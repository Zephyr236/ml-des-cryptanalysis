#!/usr/bin/env python3
"""Run the exact log-DDT chunk-ranking baseline.

    python scripts/ddt_rank.py --config configs/eval/ddt-rank-des4-kpa.yaml

The script measures whether a classical DDT counter can rank the true
last-round 6-bit chunk above chance on key-disjoint test keys.  It is the
baseline that the SPADE residual must beat (F2 in ADR-0006).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from des_ml.data import SPLIT_TEST  # noqa: E402
from des_ml.eval.ddt_rank import (  # noqa: E402
    chunk_scores,
    make_pairs,
    rank_stats,
    ranks,
    sample_keys,
    true_chunks,
)
from des_ml.manifest import RunWriter, update_latest  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", default="results/stage1")
    parser.add_argument("--device", default=None)
    parser.add_argument("--keys", type=int, default=None)
    parser.add_argument("--pairs", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.keys is not None:
        config["keys"] = args.keys
    if args.pairs is not None:
        config["pairs"] = args.pairs
    if args.seed is not None:
        config["seed"] = args.seed
    delta = config.get("delta")
    if isinstance(delta, str):
        delta = int(delta, 0)
        config["delta"] = delta

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    seed = int(config.get("seed", 0))
    generator = torch.Generator(device=device)
    generator.manual_seed(seed)
    torch.manual_seed(seed)

    writer = RunWriter(
        stage_dir=REPO_ROOT / args.out,
        config=config,
        config_path=args.config,
        seed=seed,
        command="python scripts/ddt_rank.py " + " ".join(sys.argv[1:]),
        repo_root=REPO_ROOT,
        tags={
            "stage": "stage1",
            "kind": "ddt-rank",
            "rounds": int(config["rounds"]),
            "mode": str(config["mode"]),
        },
    )

    keys = sample_keys(
        int(config["keys"]), split=SPLIT_TEST, device=device, generator=generator
    )
    ciphertext1, ciphertext2 = make_pairs(
        keys,
        int(config["pairs"]),
        rounds=int(config["rounds"]),
        mode=str(config["mode"]),
        delta=delta,
        generator=generator,
        device=device,
    )
    scores = chunk_scores(ciphertext1, ciphertext2)
    truth = true_chunks(keys, int(config["rounds"]))
    stats = rank_stats(scores, truth)

    per_sbox = [float(value) for value in ranks(scores, truth).mean(dim=0).tolist()]
    (writer.path / "per_sbox.json").write_text(
        json.dumps({"mean_rank_per_sbox": per_sbox}, indent=2), encoding="utf-8"
    )

    metrics = {
        **stats,
        "rounds": float(config["rounds"]),
        "keys": float(config["keys"]),
        "pairs_per_key": float(config["pairs"]),
        "delta_is_zero": 0.0 if delta is None else float(int(delta) == 0),
    }
    writer.log(json.dumps(metrics, indent=2, sort_keys=True))
    writer.record(0, metrics)
    manifest = writer.finish(status="completed", final=metrics)
    update_latest(REPO_ROOT / "results", writer.path, manifest)
    print(json.dumps({"run_dir": str(writer.path), "metrics": metrics}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
