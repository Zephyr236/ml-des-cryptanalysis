#!/usr/bin/env python3
"""Key recovery with a trained chunk scorer.

For each held-out target key:
1. Score all 64 candidates per S-box on ``pairs`` known/chosen pairs.
2. Take the top ``top`` candidates per S-box and enumerate the product.
3. Invert the key schedule for each 48-bit round key (256 completions).
4. Verify every master key with real re-encryption on fresh plaintexts.

Only re-encryption counts as success.  The run reports success rate and
the number of key-schedule candidates examined.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from des_ml.data import SPLIT_TEST, SPLIT_VAL  # noqa: E402
from des_ml.des_torch import des_encrypt_torch, key_schedule_torch, rand64  # noqa: E402
from des_ml.eval.ddt_rank import log_ddt_tensor, sample_keys, sbox_lut  # noqa: E402
from des_ml.key_schedule import recover_master_keys  # noqa: E402
from des_ml.manifest import RunWriter, update_latest  # noqa: E402
from des_ml.models.chunk_scorer import ChunkScorer, candidate_log_ddt  # noqa: E402
from des_ml.train.train_chunk_scorer import make_batch  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", default="results/stage2")
    parser.add_argument("--keys", type=int, default=8, help="target keys to attack")
    parser.add_argument("--pairs", type=int, default=None, help="pairs used for scoring")
    parser.add_argument("--top", type=int, default=3, help="candidates per trusted S-box")
    parser.add_argument(
        "--known-boxes",
        type=int,
        default=8,
        help="number of S-boxes ranked by the model; the rest are enumerated fully",
    )
    parser.add_argument("--eval-keys", type=int, default=8)
    parser.add_argument("--max-combos", type=float, default=2_000_000)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-latest", action="store_true")
    parser.add_argument("--analyze-only", action="store_true")
    return parser.parse_args()


def make_pairs(config: dict, key: torch.Tensor, pairs: int, device: torch.device, generator):
    rounds = int(config["rounds"])
    mode = str(config["mode"])
    delta = config.get("delta")
    if isinstance(delta, str):
        delta = int(delta, 0)
    keys = key.repeat(pairs)
    plaintext1 = rand64(pairs, device=device, generator=generator)
    if mode == "cpa":
        plaintext2 = plaintext1 ^ int(delta)
    else:
        plaintext2 = rand64(pairs, device=device, generator=generator)
    ciphertext1 = des_encrypt_torch(plaintext1, keys, rounds)
    ciphertext2 = des_encrypt_torch(plaintext2, keys, rounds)
    return (
        plaintext1.unsqueeze(0),
        plaintext2.unsqueeze(0),
        ciphertext1.unsqueeze(0),
        ciphertext2.unsqueeze(0),
    )


def verify_candidates(
    candidates: list[int],
    verifier_plain: torch.Tensor,
    verifier_cipher: torch.Tensor,
    rounds: int,
    device: torch.device,
) -> int | None:
    if not candidates:
        return None
    signed = [value - (1 << 64) if value >= (1 << 63) else value for value in candidates]
    keys = torch.tensor(signed, dtype=torch.long, device=device)
    matched = torch.ones(len(candidates), dtype=torch.bool, device=device)
    for plain, cipher in zip(verifier_plain, verifier_cipher, strict=True):
        blocks = torch.full_like(keys, int(plain))
        matched &= des_encrypt_torch(blocks, keys, rounds) == int(cipher)
        if not bool(matched.any()):
            return None
    indices = torch.nonzero(matched, as_tuple=False).flatten()
    if len(indices) == 0:
        return None
    return int(indices[0].item())


def main() -> int:
    args = parse_args()
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    config = checkpoint["config"]
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    rounds = int(config["rounds"])
    pairs = int(args.pairs or config["train"].get("eval_pairs", 64))
    generator = torch.Generator(device=device)
    generator.manual_seed(args.seed)

    model = ChunkScorer(
        hidden=int(config.get("model", {}).get("hidden", 256)),
        dropout=0.0,
        sbox_lut=sbox_lut(),
        log_ddt=log_ddt_tensor(),
    ).to(device)
    model.load_state_dict(checkpoint["model"])
    model.eval()

    writer = RunWriter(
        stage_dir=REPO_ROOT / args.out,
        config={
            "checkpoint": str(args.checkpoint),
            "keys": args.keys,
            "pairs": pairs,
            "top": args.top,
            "known_boxes": args.known_boxes,
            "rounds": rounds,
        },
        config_path="scripts/chunk_key_recovery.py",
        seed=args.seed,
        command="python scripts/chunk_key_recovery.py " + " ".join(sys.argv[1:]),
        repo_root=REPO_ROOT,
        tags={"stage": "stage2", "kind": "chunk-key-recovery", "rounds": rounds},
    )

    @torch.no_grad()
    def box_accuracy() -> list[float]:
        p1, p2, c1, c2, truth = make_batch(
            config,
            split=SPLIT_VAL,
            device=device,
            generator=generator,
            n_keys=args.eval_keys,
            pairs=pairs,
        )
        logits = model(p1, p2, c1, c2)
        correct = (logits.argmax(dim=-1) == truth).float().mean(dim=0)
        return [float(value) for value in correct.tolist()]

    box_acc = box_accuracy()
    trusted = sorted(range(8), key=lambda j: box_acc[j], reverse=True)[: args.known_boxes]
    writer.log(f"box_acc={box_acc} trusted={trusted}")

    target_keys = sample_keys(args.keys, split=SPLIT_TEST, device="cpu")
    successes = 0
    details = []
    with torch.no_grad():
        for index, key in enumerate(target_keys.tolist()):
            key_tensor = torch.tensor([key], dtype=torch.long, device=device)
            p1, p2, c1, c2 = make_pairs(config, key_tensor, pairs, device, generator)
            logits = model(p1, p2, c1, c2)[0]  # (8, 64)
            round_key = key_schedule_torch(key_tensor, rounds)[-1]
            truth = torch.stack(
                [(round_key >> (42 - 6 * j)) & 0x3F for j in range(8)], dim=1
            )[0]
            true_scores = logits.gather(1, truth.unsqueeze(1)).squeeze(1)
            ranks = 1.0 + (logits > true_scores.unsqueeze(1)).sum(dim=1).float() + (
                (logits == true_scores.unsqueeze(1)).sum(dim=1).float() - 1.0
            ) / 2.0
            ddt_logits = candidate_log_ddt(c1, c2, model.sbox_lut, model.log_ddt)[0]
            ddt_true = ddt_logits.gather(1, truth.unsqueeze(1)).squeeze(1)
            ddt_ranks = 1.0 + (ddt_logits > ddt_true.unsqueeze(1)).sum(dim=1).float() + (
                (ddt_logits == ddt_true.unsqueeze(1)).sum(dim=1).float() - 1.0
            ) / 2.0
            top = torch.topk(logits, args.top, dim=-1).indices  # (8, top)
            if args.analyze_only:
                details.append(
                    {
                        "key": f"0x{key & ((1 << 64) - 1):016X}",
                        "success": False,
                        "candidates_tried": 0,
                        "ranks": [float(value) for value in ranks.tolist()],
                        "ddt_ranks": [float(value) for value in ddt_ranks.tolist()],
                    }
                )
                continue
            candidates_per_sbox = [
                top[j].tolist() if j in trusted else list(range(64)) for j in range(8)
            ]
            combos = 1
            for values in candidates_per_sbox:
                combos *= len(values)
            if combos > args.max_combos:
                raise RuntimeError(
                    f"candidate product {combos} exceeds --max-combos {args.max_combos}"
                )

            verifier_plain = rand64(2, device=device, generator=generator)
            verifier_cipher = des_encrypt_torch(
                verifier_plain,
                torch.full((2,), key, dtype=torch.long, device=device),
                rounds,
            )

            tried = 0
            found = None
            buffer: list[int] = []
            for combo in itertools.product(*candidates_per_sbox):
                round_key = 0
                for j, chunk in enumerate(combo):
                    round_key |= int(chunk) << (42 - 6 * j)
                buffer.extend(recover_master_keys(round_key, rounds))
                tried += 256
                if len(buffer) >= 65536:
                    hit = verify_candidates(buffer, verifier_plain, verifier_cipher, rounds, device)
                    buffer = []
                    if hit is not None:
                        found = hit
                        break
            if found is None:
                hit = verify_candidates(buffer, verifier_plain, verifier_cipher, rounds, device)
                if hit is not None:
                    found = hit
            success = found is not None
            successes += int(success)
            details.append(
                {
                    "key": f"0x{key & ((1 << 64) - 1):016X}",
                    "success": success,
                    "candidates_tried": tried,
                    "ranks": [float(value) for value in ranks.tolist()],
                    "ddt_ranks": [float(value) for value in ddt_ranks.tolist()],
                }
            )
            writer.log(f"key={index} success={success} tried={tried}")

    metrics = {
        "success_rate": successes / len(target_keys),
        "successes": float(successes),
        "keys": float(len(target_keys)),
        "pairs": float(pairs),
        "top": float(args.top),
        "known_boxes": float(args.known_boxes),
        "rounds": float(rounds),
    }
    (writer.path / "key_recovery.json").write_text(
        json.dumps({"box_accuracy": box_acc, "trusted": trusted, "details": details}, indent=2),
        encoding="utf-8",
    )
    writer.record(0, metrics)
    manifest = writer.finish(status="completed", final=metrics)
    if not args.no_latest:
        update_latest(REPO_ROOT / "results", writer.path, manifest)
    print(json.dumps({"run_dir": str(writer.path), "metrics": metrics}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
