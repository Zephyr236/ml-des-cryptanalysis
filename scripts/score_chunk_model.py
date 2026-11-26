#!/usr/bin/env python3
"""Save a trained chunk scorer's per-candidate scores for one key."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from des_ml.des_torch import des_encrypt_torch, key_schedule_torch, rand64  # noqa: E402
from des_ml.eval.ddt_rank import log_ddt_tensor, sbox_lut  # noqa: E402
from des_ml.models.chunk_scorer import ChunkScorer  # noqa: E402
from des_ml.models.chunk_scorer_legacy import LegacyChunkScorer  # noqa: E402


def make_pairs(config, key, pairs, device, generator):
    rounds = int(config["rounds"])
    mode = str(config["mode"])
    delta = config.get("delta")
    if isinstance(delta, str):
        delta = int(delta, 0)
    keys = key.repeat(pairs)
    plaintext1 = rand64(pairs, device=device, generator=generator)
    plaintext2 = plaintext1 ^ int(delta) if mode == "cpa" else rand64(pairs, device=device, generator=generator)
    ciphertext1 = des_encrypt_torch(plaintext1, keys, rounds)
    ciphertext2 = des_encrypt_torch(plaintext2, keys, rounds)
    return plaintext1.unsqueeze(0), plaintext2.unsqueeze(0), ciphertext1.unsqueeze(0), ciphertext2.unsqueeze(0)


def signed(value: int) -> int:
    return value - (1 << 64) if value >= (1 << 63) else value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--pairs", type=int, default=64)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    config = checkpoint["config"]
    rounds = int(config["rounds"])
    model_class = (
        LegacyChunkScorer
        if "sbox_embedding.weight" in checkpoint["model"]
        else ChunkScorer
    )
    model = model_class(
        hidden=int(config.get("model", {}).get("hidden", 256)),
        dropout=0.0,
        sbox_lut=sbox_lut(),
        log_ddt=log_ddt_tensor(),
    ).to(device)
    model.load_state_dict(checkpoint["model"])
    model.eval()
    key = int(args.key, 0) & ((1 << 64) - 1)
    generator = torch.Generator(device=device)
    generator.manual_seed(args.seed)
    key_tensor = torch.tensor([signed(key)], dtype=torch.long, device=device)
    p1, p2, c1, c2 = make_pairs(config, key_tensor, args.pairs, device, generator)
    with torch.no_grad():
        logits = model(p1, p2, c1, c2)[0]
    round_key = key_schedule_torch(key_tensor, rounds)[-1]
    truth = torch.stack(
        [(round_key >> (42 - 6 * j)) & 0x3F for j in range(8)], dim=1
    )[0]
    true_scores = logits.gather(1, truth.unsqueeze(1)).squeeze(1)
    ranks = 1.0 + (logits > true_scores.unsqueeze(1)).sum(dim=1).float() + (
        (logits == true_scores.unsqueeze(1)).sum(dim=1).float() - 1.0
    ) / 2.0
    payload = {
        "scores": logits.cpu().tolist(),
        "details": {
            "true_chunks": [int(v) for v in truth.tolist()],
            "ranks": [float(v) for v in ranks.tolist()],
        },
        "key": f"0x{key:016X}",
        "rounds": rounds,
        "checkpoint": str(args.checkpoint),
        "pairs": args.pairs,
    }
    Path(args.out).write_text(json.dumps(payload), encoding="utf-8")
    print(json.dumps({"out": args.out, "key": payload["key"], "ranks": payload["details"]["ranks"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
