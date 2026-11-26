"""Train a neural distinguisher for round-reduced DES.

Usage
-----
    python -m des_ml.train.train_distinguisher \
        --config configs/distinguisher/des4-kpa.yaml \
        --out results/stage1

The script writes a complete, CI-verifiable result directory: the
resolved config, a JSONL metric log, a human-readable log, an optional
checkpoint, ``metrics.json`` and ``manifest.json``.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import torch
import yaml
from torch import nn
from torch.nn import functional as F

from des_ml.data import SPLIT_VERSION, PairStream
from des_ml.manifest import RunWriter
from des_ml.metrics import binary_accuracy, roc_auc
from des_ml.models.pair_cnn import build_model

REPO_ROOT = Path(__file__).resolve().parents[3]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Path to a YAML experiment config")
    parser.add_argument("--out", default="results/stage1", help="Stage directory for results")
    parser.add_argument("--max-steps", type=int, default=None, help="Override train.steps (smoke runs)")
    parser.add_argument("--device", default=None, help="cuda, cpu, or auto")
    parser.add_argument("--seed", type=int, default=None, help="Override train.seed")
    parser.add_argument("--no-checkpoint", action="store_true", help="Do not write model weights")
    return parser.parse_args(argv)


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("config must be a mapping")
    return config


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def resolve_device(requested: str | None) -> torch.device:
    if requested in (None, "auto"):
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(requested)


def make_stream(config: dict, *, split: int, seed: int, device: torch.device) -> PairStream:
    data_cfg = config.get("data", {})
    delta = config.get("delta")
    if isinstance(delta, str):
        delta = int(delta, 0)
    return PairStream(
        rounds=int(config["rounds"]),
        mode=str(config["mode"]),
        split=split,
        batch_size=int(config["train"]["batch_size"]),
        device=device,
        seed=seed,
        negative_fraction=float(data_cfg.get("negative_fraction", 0.5)),
        delta=delta,
    )


@torch.no_grad()
def evaluate(model: nn.Module, stream: PairStream, batches: int, device: torch.device) -> dict[str, float]:
    model.eval()
    losses: list[float] = []
    scores: list[torch.Tensor] = []
    labels: list[torch.Tensor] = []
    for _ in range(batches):
        batch = stream.batch().to(device)
        logits = model(batch.to_planes())
        loss = F.binary_cross_entropy_with_logits(logits, batch.labels.float())
        losses.append(float(loss.item()))
        scores.append(torch.sigmoid(logits).detach().cpu())
        labels.append(batch.labels.detach().cpu())
    model.train()
    scores_t = torch.cat(scores)
    labels_t = torch.cat(labels)
    return {
        "val_loss": float(np.mean(losses)),
        "val_acc": binary_accuracy(labels_t, scores_t),
        "val_auc": roc_auc(labels_t.numpy(), scores_t.numpy()),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config)
    config = load_config(config_path)
    train_cfg = config["train"]
    seed = int(args.seed if args.seed is not None else train_cfg.get("seed", 0))
    steps = int(args.max_steps if args.max_steps is not None else train_cfg["steps"])
    device = resolve_device(args.device or train_cfg.get("device"))

    set_seed(seed)
    torch.backends.cudnn.benchmark = False

    command = "python -m des_ml.train.train_distinguisher " + " ".join(sys.argv[1:])
    writer = RunWriter(
        stage_dir=REPO_ROOT / args.out,
        config=config,
        config_path=str(config_path),
        seed=seed,
        command=command,
        repo_root=REPO_ROOT,
        tags={
            "rounds": int(config["rounds"]),
            "mode": str(config["mode"]),
            "model": str(config.get("model", {}).get("name", "pair_cnn")),
            "split": SPLIT_VERSION,
        },
    )
    writer.log(f"run_id={writer.run_id} device={device} seed={seed} steps={steps}")

    model = build_model(config.get("model", {})).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(train_cfg.get("lr", 1e-3)),
        weight_decay=float(train_cfg.get("weight_decay", 1e-2)),
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(steps, 1))

    train_stream = make_stream(config, split=0, seed=seed, device=device)
    val_stream = make_stream(config, split=1, seed=seed + 1_000_003, device=device)

    log_every = int(train_cfg.get("log_every", 50))
    eval_every = int(train_cfg.get("eval_every", 250))
    eval_batches = int(train_cfg.get("eval_batches", 16))
    best_acc = -math.inf
    best_step = 0
    final_metrics: dict[str, float] = {}

    try:
        model.train()
        for step in range(1, steps + 1):
            batch = train_stream.batch().to(device)
            logits = model(batch.to_planes())
            loss = F.binary_cross_entropy_with_logits(logits, batch.labels.float())
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()

            if step % log_every == 0 or step == 1:
                message = f"step={step} train_loss={loss.item():.6f} lr={scheduler.get_last_lr()[0]:.2e}"
                writer.log(message)
                print(message, flush=True)

            if step % eval_every == 0 or step == steps:
                metrics = evaluate(model, val_stream, eval_batches, device)
                metrics["train_loss"] = float(loss.item())
                metrics["lr"] = float(scheduler.get_last_lr()[0])
                writer.record(step, metrics)
                message = (
                    f"eval step={step} val_loss={metrics['val_loss']:.6f} "
                    f"val_acc={metrics['val_acc']:.4f} val_auc={metrics['val_auc']:.4f}"
                )
                writer.log(message)
                print(message, flush=True)
                if metrics["val_acc"] > best_acc:
                    best_acc = metrics["val_acc"]
                    best_step = step
                    if not args.no_checkpoint:
                        torch.save(
                            {"model": model.state_dict(), "config": config, "step": step},
                            writer.path / "best.pt",
                        )
                final_metrics = metrics

        final_metrics["best_val_acc"] = best_acc
        final_metrics["best_step"] = float(best_step)
        manifest = writer.finish(status="completed", final=final_metrics)
        print(json.dumps({"run_dir": str(writer.path), "run_id": manifest["run_id"]}, indent=2))
        return 0
    except Exception as exc:  # pragma: no cover - failure path exercised in CI
        writer.log(f"FAILED: {type(exc).__name__}: {exc}")
        writer.finish(status="failed", final=final_metrics, extra={"error": str(exc)})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
