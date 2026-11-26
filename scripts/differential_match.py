#!/usr/bin/env python3
"""Characteristic-match key recovery for 6-round DES.

Unlike the log-DDT ranker, which scores each pair by the probability of
its observed last-round output difference, this script tests whether a
candidate chunk key makes the partially decrypted state match the
trail's predicted L5 difference.  That is the standard differential
right-pair test and does not let high-probability wrong differences
dilute a handful of right pairs.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from des_ml.des import P  # noqa: E402
from des_ml.des_torch import des_encrypt_torch, key_schedule_torch, permute_torch, rand64  # noqa: E402
from des_ml.eval.ddt_rank import sbox_lut  # noqa: E402
from des_ml.key_schedule import recover_master_keys  # noqa: E402
from des_ml.last_round import chunk_positions  # noqa: E402
from des_ml.manifest import RunWriter, update_latest  # noqa: E402
from des_ml.models.chunk_scorer import last_round_context, sbox_inputs  # noqa: E402

MASK64 = (1 << 64) - 1
MASK32 = 0xFFFFFFFF


def signed(value: int) -> int:
    return value - (1 << 64) if value >= (1 << 63) else value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    parser.add_argument("--delta", required=True)
    parser.add_argument("--trail-l5", required=True, help="predicted L5 difference")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--pairs", type=int, default=100_000_000)
    parser.add_argument("--batch", type=int, default=1 << 16)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--filter-vector", required=True)
    parser.add_argument("--top-k", type=int, default=1)
    parser.add_argument("--full-boxes", default="")
    parser.add_argument("--max-combos", type=float, default=2_000_000)
    parser.add_argument("--out", default="results/stage2")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-latest", action="store_true")
    args = parser.parse_args()

    key = int(args.key, 0) & MASK64
    delta = int(args.delta, 0) & MASK64
    trail_l5 = int(args.trail_l5, 0) & MASK32
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    generator = torch.Generator(device=device)
    generator.manual_seed(args.seed)
    lut = sbox_lut().to(device)

    filter_values = [int(value.strip()) for value in args.filter_vector.split(",")]
    if len(filter_values) != 8:
        raise ValueError("--filter-vector must have eight values")
    filter_vector = torch.tensor(filter_values, dtype=torch.long, device=device)
    filter_active = filter_vector >= 0
    full_boxes = {
        int(value.strip()) for value in args.full_boxes.split(",") if value.strip()
    }

    key_tensor = torch.tensor([signed(key)], dtype=torch.long, device=device)
    round_key = key_schedule_torch(key_tensor, args.rounds)[-1]
    truth = torch.stack(
        [(round_key >> (42 - 6 * j)) & 0x3F for j in range(8)], dim=1
    )[0]
    positions = [chunk_positions(j) for j in range(8)]
    target_bits = [
        torch.tensor(
            [(trail_l5 >> (31 - position)) & 1 for position in positions[j]],
            dtype=torch.long,
            device=device,
        )
        for j in range(8)
    ]

    writer = RunWriter(
        stage_dir=REPO_ROOT / args.out,
        config={
            "key": args.key,
            "delta": args.delta,
            "trail_l5": args.trail_l5,
            "rounds": args.rounds,
            "pairs": args.pairs,
            "batch": args.batch,
            "filter_vector": args.filter_vector,
            "top_k": args.top_k,
            "full_boxes": args.full_boxes,
            "score": "trail-match",
        },
        config_path="scripts/differential_match.py",
        seed=args.seed,
        command="python scripts/differential_match.py " + " ".join(sys.argv[1:]),
        repo_root=REPO_ROOT,
        tags={"stage": "stage2", "kind": "differential-match", "rounds": args.rounds},
    )

    counts = torch.zeros((8, 64), dtype=torch.long, device=device)
    filtered_pairs = 0
    start = time.perf_counter()
    done = 0
    candidates = torch.arange(64, device=device)
    while done < args.pairs:
        n = min(args.batch, args.pairs - done)
        plaintext1 = rand64(n, device=device, generator=generator)
        plaintext2 = plaintext1 ^ signed(delta)
        keys = key_tensor.expand(n)
        ciphertext1 = des_encrypt_torch(plaintext1, keys, args.rounds).reshape(1, n)
        ciphertext2 = des_encrypt_torch(plaintext2, keys, args.rounds).reshape(1, n)
        with torch.no_grad():
            right1, left1, right2, left2 = last_round_context(ciphertext1, ciphertext2)
            inputs1 = sbox_inputs(left1)
            inputs2 = sbox_inputs(left2)
            difference = inputs1 ^ inputs2
            mask = ((difference == filter_vector) | (~filter_active)).all(dim=-1)[0]
            kept = int(mask.sum().item())
            filtered_pairs += kept
            if kept:
                r1 = right1[:, mask]
                r2 = right2[:, mask]
                l1 = left1[:, mask]
                l2 = left2[:, mask]
                rdiff = r1 ^ r2
                inputs1 = sbox_inputs(l1)
                inputs2 = sbox_inputs(l2)
                for j in range(8):
                    u1 = inputs1[..., j]
                    u2 = inputs2[..., j]
                    outputs = (
                        lut[j][u1.unsqueeze(-1) ^ candidates]
                        ^ lut[j][u2.unsqueeze(-1) ^ candidates]
                    )
                    prep = outputs << (28 - 4 * j)
                    corrected = rdiff.unsqueeze(-1) ^ permute_torch(prep, P, 32)
                    match = torch.ones_like(corrected, dtype=torch.bool)
                    for bit_index, position in enumerate(positions[j]):
                        match &= ((corrected >> (31 - position)) & 1) == target_bits[j][bit_index]
                    counts[j] += match.sum(dim=0)
        done += n
        if done % (args.batch * 20) == 0 or done == args.pairs:
            elapsed = time.perf_counter() - start
            message = f"pairs={done} kept={filtered_pairs} rate={done / elapsed:.0f}/s"
            writer.log(message)
            print(message, flush=True)

    true_scores = counts.gather(1, truth.unsqueeze(1)).squeeze(1)
    greater = (counts > true_scores.unsqueeze(1)).sum(dim=1)
    equal = (counts == true_scores.unsqueeze(1)).sum(dim=1)
    ranks = 1.0 + greater.double() + (equal.double() - 1.0) / 2.0
    metrics = {
        "rounds": float(args.rounds),
        "pairs": float(args.pairs),
        "elapsed_s": float(time.perf_counter() - start),
        "mean_rank": float(ranks.mean()),
        "top1": float((ranks <= 1).double().mean()),
        "filtered_pairs": float(filtered_pairs),
    }
    details = {
        "true_chunks": [int(value) for value in truth.tolist()],
        "ranks": [float(value) for value in ranks.tolist()],
    }
    (writer.path / "scores.json").write_text(
        json.dumps({"scores": counts.cpu().tolist(), "details": details}),
        encoding="utf-8",
    )

    topk = torch.topk(counts, args.top_k, dim=1).indices
    candidate_lists = [
        list(range(64)) if j in full_boxes else topk[j].tolist() for j in range(8)
    ]
    combos = 1
    for values in candidate_lists:
        combos *= len(values)
    recovered = False
    if combos <= args.max_combos:
        verifier_plain = rand64(4, device=device, generator=generator)
        verifier_cipher = des_encrypt_torch(
            verifier_plain, key_tensor.expand(4), args.rounds
        )
        found = None
        plain_batched = verifier_plain.repeat(256)
        cipher_batched = verifier_cipher.unsqueeze(0)
        for combo in itertools.product(*candidate_lists):
            round_key = sum(int(chunk) << (42 - 6 * j) for j, chunk in enumerate(combo))
            candidates_master = recover_master_keys(round_key, args.rounds)
            keys_batch = torch.tensor(
                [signed(value) for value in candidates_master],
                dtype=torch.long,
                device=device,
            )
            outputs = des_encrypt_torch(
                plain_batched, keys_batch.repeat_interleave(4), args.rounds
            ).reshape(len(candidates_master), 4)
            matched = (outputs == cipher_batched).all(dim=1)
            if bool(matched.any()):
                found = candidates_master[int(torch.nonzero(matched)[0].item())]
                break
        recovered = found is not None
        details["master_key"] = f"0x{found:016X}" if found is not None else ""
        details["combos_tried"] = combos
    metrics["recovered"] = float(recovered)
    (writer.path / "scores.json").write_text(
        json.dumps({"scores": counts.cpu().tolist(), "details": details}),
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
