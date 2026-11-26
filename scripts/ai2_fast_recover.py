#!/usr/bin/env python3
"""Vectorised 2-round AI key recovery.

The 2-round key schedule observes 48 of the 56 effective-key bits; the
remaining 8 positions are fixed.  For each K2 candidate combination we
build a base key, then verify all 2^8 completions in 256 batched GPU
calls instead of 262144 per-combo calls.
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

from des_ml.des import PC1, PC2  # noqa: E402
from des_ml.des_torch import des_encrypt_torch, rand64  # noqa: E402
from des_ml.key_schedule import round_key_master_positions  # noqa: E402
from des_ml.manifest import RunWriter, update_latest  # noqa: E402


def signed(value: int) -> int:
    return value - (1 << 64) if value >= (1 << 63) else value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--top-k", type=int, default=2)
    parser.add_argument("--known-boxes", type=int, default=8)
    parser.add_argument("--full-boxes", default="3,5")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="results/stage2")
    parser.add_argument("--no-latest", action="store_true")
    args = parser.parse_args()

    payload = json.loads(Path(args.scores).read_text(encoding="utf-8"))
    scores = torch.tensor(payload["scores"], dtype=torch.float64)
    top = torch.topk(scores, args.top_k, dim=1).indices
    full_boxes = {int(v.strip()) for v in args.full_boxes.split(",") if v.strip()}
    candidate_lists = [
        list(range(64)) if j in full_boxes else top[j].tolist() for j in range(8)
    ]
    combos = list(itertools.product(*candidate_lists))
    k2s = [
        sum(int(chunk) << (42 - 6 * j) for j, chunk in enumerate(combo))
        for combo in combos
    ]

    positions = round_key_master_positions(args.rounds)
    unknown_cd = [p for p in range(1, 57) if p not in set(PC2)]
    unknown_master = [PC1[p - 1] for p in unknown_cd]
    base = []
    for k2 in k2s:
        value = 0
        for bit_index, position in enumerate(positions):
            if (k2 >> (47 - bit_index)) & 1:
                value |= 1 << (64 - position)
        base.append(value)
    masks = []
    for assignment in range(256):
        value = 0
        for index, position in enumerate(unknown_master):
            if (assignment >> index) & 1:
                value |= 1 << (64 - position)
        masks.append(value)

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    key = int(args.key, 0) & ((1 << 64) - 1)
    generator = torch.Generator(device=device)
    generator.manual_seed(args.seed)
    verifier_plain = rand64(4, device=device, generator=generator)
    target = torch.tensor([signed(key)], dtype=torch.long, device=device)
    verifier_cipher = des_encrypt_torch(verifier_plain, target.expand(4), args.rounds)

    base_tensor = torch.tensor([signed(v) for v in base], dtype=torch.long, device=device)
    plain_batched = verifier_plain.repeat(len(base))
    cipher_batched = verifier_cipher.unsqueeze(0)
    found = None
    tried = 0
    for mask in masks:
        keys = base_tensor | mask
        outputs = des_encrypt_torch(
            plain_batched, keys.repeat_interleave(4), args.rounds
        ).reshape(len(base), 4)
        matched = (outputs == cipher_batched).all(dim=1)
        tried += len(base)
        if bool(matched.any()):
            index = int(torch.nonzero(matched)[0].item())
            found = base[index] | mask
            break

    metrics = {
        "rounds": float(args.rounds),
        "combos": float(len(base)),
        "candidates_tried": float(tried),
        "recovered": float(found is not None),
    }
    writer = RunWriter(
        stage_dir=REPO_ROOT / args.out,
        config={
            "scores": args.scores,
            "key": args.key,
            "top_k": args.top_k,
            "full_boxes": args.full_boxes,
            "rounds": args.rounds,
            "combo_start": 0,
            "combo_count": len(base),
        },
        config_path="scripts/ai2_fast_recover.py",
        seed=args.seed,
        command="python scripts/ai2_fast_recover.py " + " ".join(sys.argv[1:]),
        repo_root=REPO_ROOT,
        tags={"stage": "stage2", "kind": "ai2-fast-recovery", "rounds": args.rounds},
    )
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
