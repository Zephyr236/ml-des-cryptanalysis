#!/usr/bin/env python3
"""Exact log-DDT ranking of last-round chunks with a differential trail.

Streams pairs under one target key, accumulates the per-candidate log-DDT
score for every S-box, and reports the rank of the true chunk.  If every
true chunk is the top candidate, the last-round key is inverted and the
recovered master key is verified by real re-encryption.
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

from des_ml.des_torch import des_encrypt_torch, key_schedule_torch, rand64  # noqa: E402
from des_ml.eval.ddt_rank import log_ddt_tensor, sbox_lut  # noqa: E402
from des_ml.key_schedule import recover_master_keys  # noqa: E402
from des_ml.manifest import RunWriter, update_latest  # noqa: E402
from des_ml.models.chunk_scorer import (  # noqa: E402
    candidate_log_ddt,
    last_round_context,
    sbox_inputs,
)

MASK64 = (1 << 64) - 1


def signed(value: int) -> int:
    return value - (1 << 64) if value >= (1 << 63) else value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True, help="target key, e.g. 0x1334...")
    parser.add_argument("--delta", required=True, help="plaintext difference, e.g. 0x1010000000")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--pairs", type=int, default=10_000_000)
    parser.add_argument("--batch", type=int, default=1 << 16)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--out", default="results/stage2")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--filter-vector",
        default=None,
        help="comma-separated eight last-round S-box input differences; keep matching pairs",
    )
    parser.add_argument("--top-k", type=int, default=1, help="candidates per S-box for key recovery")
    parser.add_argument("--max-combos", type=float, default=2_000_000)
    parser.add_argument("--no-latest", action="store_true")
    args = parser.parse_args()

    key = int(args.key, 0) & MASK64
    delta = int(args.delta, 0) & MASK64
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    generator = torch.Generator(device=device)
    generator.manual_seed(args.seed)
    lut = sbox_lut().to(device)
    log_ddt = log_ddt_tensor().to(device)

    key_tensor = torch.tensor([signed(key)], dtype=torch.long, device=device)
    round_key = key_schedule_torch(key_tensor, args.rounds)[-1]
    truth = torch.stack(
        [(round_key >> (42 - 6 * j)) & 0x3F for j in range(8)], dim=1
    )[0]

    writer = RunWriter(
        stage_dir=REPO_ROOT / args.out,
        config={
            "key": args.key,
            "delta": args.delta,
            "rounds": args.rounds,
            "pairs": args.pairs,
            "batch": args.batch,
        },
        config_path="scripts/differential_rank.py",
        seed=args.seed,
        command="python scripts/differential_rank.py " + " ".join(sys.argv[1:]),
        repo_root=REPO_ROOT,
        tags={"stage": "stage2", "kind": "differential-rank", "rounds": args.rounds},
    )

    filter_vector = None
    if args.filter_vector:
        values = [int(value.strip()) for value in args.filter_vector.split(",")]
        if len(values) != 8:
            raise ValueError("--filter-vector must have eight values")
        filter_vector = torch.tensor(values, dtype=torch.long, device=device)
    scores = torch.zeros((8, 64), dtype=torch.float64, device=device)
    filtered_pairs = 0
    start = time.perf_counter()
    done = 0
    while done < args.pairs:
        n = min(args.batch, args.pairs - done)
        plaintext1 = rand64(n, device=device, generator=generator)
        plaintext2 = plaintext1 ^ signed(delta)
        keys = key_tensor.expand(n)
        ciphertext1 = des_encrypt_torch(plaintext1, keys, args.rounds).reshape(1, n)
        ciphertext2 = des_encrypt_torch(plaintext2, keys, args.rounds).reshape(1, n)
        with torch.no_grad():
            if filter_vector is not None:
                _, left1, _, left2 = last_round_context(ciphertext1, ciphertext2)
                inputs = sbox_inputs(left1) ^ sbox_inputs(left2)
                mask = (inputs == filter_vector).all(dim=-1)[0]
                kept = int(mask.sum().item())
                filtered_pairs += kept
                if kept:
                    ciphertext1 = ciphertext1[:, mask]
                    ciphertext2 = ciphertext2[:, mask]
                    scores += candidate_log_ddt(
                        ciphertext1, ciphertext2, lut, log_ddt
                    )[0].double()
            else:
                scores += candidate_log_ddt(ciphertext1, ciphertext2, lut, log_ddt)[0].double()
        done += n
        if done % (args.batch * 20) == 0 or done == args.pairs:
            elapsed = time.perf_counter() - start
            message = f"pairs={done} rate={done / elapsed:.0f}/s"
            writer.log(message)
            print(message, flush=True)

    true_scores = scores.gather(1, truth.unsqueeze(1)).squeeze(1)
    greater = (scores > true_scores.unsqueeze(1)).sum(dim=1)
    equal = (scores == true_scores.unsqueeze(1)).sum(dim=1)
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
    recovered = False
    topk = torch.topk(scores, args.top_k, dim=1).indices
    candidate_lists = [topk[j].tolist() for j in range(8)]
    combos = 1
    for values in candidate_lists:
        combos *= len(values)
    if combos <= args.max_combos:
        verifier_plain = rand64(4, device=device, generator=generator)
        verifier_cipher = des_encrypt_torch(
            verifier_plain, key_tensor.expand(4), args.rounds
        )
        found = None
        for combo in itertools.product(*candidate_lists):
            round_key = sum(int(chunk) << (42 - 6 * j) for j, chunk in enumerate(combo))
            for candidate in recover_master_keys(round_key, args.rounds):
                signed_candidate = signed(candidate)
                candidate_tensor = torch.tensor(
                    [signed_candidate], dtype=torch.long, device=device
                ).expand(4)
                if bool(
                    (
                        des_encrypt_torch(verifier_plain, candidate_tensor, args.rounds)
                        == verifier_cipher
                    ).all()
                ):
                    found = candidate
                    break
            if found is not None:
                break
        recovered = found is not None
        details["master_key"] = f"0x{found:016X}" if found is not None else ""
        details["combos_tried"] = combos
    metrics["recovered"] = float(recovered)

    (writer.path / "scores.json").write_text(
        json.dumps({"scores": scores.cpu().tolist(), "details": details}),
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
