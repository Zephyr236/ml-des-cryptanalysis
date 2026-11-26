#!/usr/bin/env python3
"""Recover a DES master key from saved per-chunk DDT scores.

The 323M-pair filtered run only needs to be executed once; this script
re-uses its ``scores.json`` to try different top-k / trusted-box
configurations without regenerating data.
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

from des_ml.des_torch import des_encrypt_torch, rand64  # noqa: E402
from des_ml.key_schedule import recover_master_keys  # noqa: E402
from des_ml.manifest import RunWriter, update_latest  # noqa: E402


def signed(value: int) -> int:
    return value - (1 << 64) if value >= (1 << 63) else value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--top-k", type=int, default=2)
    parser.add_argument("--known-boxes", type=int, default=8)
    parser.add_argument(
        "--full-boxes",
        default="",
        help="comma-separated S-box indices to enumerate fully",
    )
    parser.add_argument("--max-combos", type=float, default=2_000_000)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="results/stage2")
    parser.add_argument("--no-latest", action="store_true")
    args = parser.parse_args()

    payload = json.loads(Path(args.scores).read_text(encoding="utf-8"))
    scores = torch.tensor(payload["scores"], dtype=torch.float64)
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    key = int(args.key, 0) & ((1 << 64) - 1)
    generator = torch.Generator(device=device)
    generator.manual_seed(args.seed)

    top = torch.topk(scores, args.top_k, dim=1).indices
    trusted = list(range(args.known_boxes))
    full_boxes = {
        int(value.strip()) for value in args.full_boxes.split(",") if value.strip()
    }
    candidate_lists = [
        list(range(64)) if j in full_boxes or j not in trusted else top[j].tolist()
        for j in range(8)
    ]
    combos = 1
    for values in candidate_lists:
        combos *= len(values)
    if combos > args.max_combos:
        raise RuntimeError(f"candidate product {combos} exceeds {args.max_combos}")

    verifier_plain = rand64(4, device=device, generator=generator)
    key_tensor = torch.tensor([signed(key)], dtype=torch.long, device=device)
    verifier_cipher = des_encrypt_torch(verifier_plain, key_tensor.expand(4), args.rounds)
    plaintext_batched = verifier_plain.repeat(256)
    cipher_batched = verifier_cipher.unsqueeze(0)

    writer = RunWriter(
        stage_dir=REPO_ROOT / args.out,
        config={
            "scores": args.scores,
            "key": args.key,
            "rounds": args.rounds,
            "top_k": args.top_k,
            "known_boxes": args.known_boxes,
            "full_boxes": args.full_boxes,
        },
        config_path="scripts/recover_from_scores.py",
        seed=args.seed,
        command="python scripts/recover_from_scores.py " + " ".join(sys.argv[1:]),
        repo_root=REPO_ROOT,
        tags={"stage": "stage2", "kind": "score-recovery", "rounds": args.rounds},
    )

    found = None
    tried = 0
    for combo in itertools.product(*candidate_lists):
        round_key = sum(int(chunk) << (42 - 6 * j) for j, chunk in enumerate(combo))
        candidates = recover_master_keys(round_key, args.rounds)
        keys = torch.tensor(
            [signed(value) for value in candidates], dtype=torch.long, device=device
        )
        outputs = des_encrypt_torch(
            plaintext_batched, keys.repeat_interleave(4), args.rounds
        ).reshape(len(candidates), 4)
        matched = (outputs == cipher_batched).all(dim=1)
        tried += len(candidates)
        if bool(matched.any()):
            found = candidates[int(torch.nonzero(matched)[0].item())]
            break

    metrics = {
        "rounds": float(args.rounds),
        "top_k": float(args.top_k),
        "known_boxes": float(args.known_boxes),
        "combos": float(combos),
        "candidates_tried": float(tried),
        "recovered": float(found is not None),
    }
    writer.record(0, metrics)
    manifest = writer.finish(
        status="completed",
        final=metrics,
        extra={"master_key": f"0x{found:016X}" if found is not None else None},
    )
    if not args.no_latest:
        update_latest(REPO_ROOT / "results", writer.path, manifest)
    print(json.dumps({"run_dir": str(writer.path), "metrics": metrics, "master_key": found}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
