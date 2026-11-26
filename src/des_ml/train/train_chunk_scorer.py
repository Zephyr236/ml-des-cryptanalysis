"""Train the SPADE-style last-round chunk scorer.

The model is the exact log-DDT counter at initialisation (zero residual
head) and learns a correction from the full pair context.  A run reports
held-out chunk accuracy and rank against the DDT baseline; a key-recovery
evaluation consumes the trained scorer in a separate step.
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
from torch.nn import functional as F

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from des_ml.data import SPLIT_TRAIN, SPLIT_VAL  # noqa: E402
from des_ml.des_torch import (  # noqa: E402
    des_encrypt_torch,
    key_schedule_torch,
    rand64,
)
from des_ml.eval.ddt_rank import (  # noqa: E402
    log_ddt_tensor,
    sample_keys,
    sbox_lut,
)
from des_ml.manifest import RunWriter, update_latest  # noqa: E402
from des_ml.models.chunk_scorer import ChunkScorer, candidate_log_ddt  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", default="results/stage2")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--no-checkpoint", action="store_true")
    return parser.parse_args()


def make_batch(
    config: dict,
    *,
    split: int,
    device: torch.device,
    generator: torch.Generator,
    n_keys: int,
    pairs: int,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    rounds = int(config["rounds"])
    mode = str(config["mode"])
    delta = config.get("delta")
    if isinstance(delta, str):
        delta = int(delta, 0)
    keys = sample_keys(n_keys, split=split, device=device, generator=generator)
    repeated = keys.repeat_interleave(pairs)
    plaintext1 = rand64(n_keys * pairs, device=device, generator=generator)
    if mode == "cpa":
        plaintext2 = plaintext1 ^ int(delta)
    else:
        plaintext2 = rand64(n_keys * pairs, device=device, generator=generator)
    ciphertext1 = des_encrypt_torch(plaintext1, repeated, rounds).reshape(n_keys, pairs)
    ciphertext2 = des_encrypt_torch(plaintext2, repeated, rounds).reshape(n_keys, pairs)
    round_key = key_schedule_torch(keys, rounds)[-1]
    truth = torch.stack(
        [(round_key >> (42 - 6 * j)) & 0x3F for j in range(8)], dim=1
    )
    return (
        plaintext1.reshape(n_keys, pairs),
        plaintext2.reshape(n_keys, pairs),
        ciphertext1,
        ciphertext2,
        truth,
    )


def chunk_metrics(logits: torch.Tensor, truth: torch.Tensor) -> dict[str, float]:
    true_scores = logits.gather(2, truth.unsqueeze(-1)).squeeze(-1)
    greater = (logits > true_scores.unsqueeze(-1)).sum(dim=-1)
    equal = (logits == true_scores.unsqueeze(-1)).sum(dim=-1)
    ranks = 1.0 + greater.float() + (equal.float() - 1.0) / 2.0
    return {
        "acc": float((ranks <= 1.0).float().mean()),
        "top5": float((ranks <= 5.0).float().mean()),
        "mean_rank": float(ranks.mean()),
    }


@torch.no_grad()
def evaluate(
    model: ChunkScorer,
    config: dict,
    *,
    device: torch.device,
    generator: torch.Generator,
) -> dict[str, float]:
    model.eval()
    train_cfg = config["train"]
    p1, p2, c1, c2, truth = make_batch(
        config,
        split=SPLIT_VAL,
        device=device,
        generator=generator,
        n_keys=int(train_cfg.get("eval_keys", 64)),
        pairs=int(train_cfg.get("eval_pairs", 64)),
    )
    logits = model(p1, p2, c1, c2)
    ddt = candidate_log_ddt(c1, c2, model.sbox_lut, model.log_ddt)
    metrics = {f"model_{k}": v for k, v in chunk_metrics(logits, truth).items()}
    metrics.update({f"ddt_{k}": v for k, v in chunk_metrics(ddt, truth).items()})
    model.train()
    return metrics


def main() -> int:
    args = parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    train_cfg = config["train"]
    seed = int(args.seed if args.seed is not None else train_cfg.get("seed", 0))
    steps = int(args.max_steps if args.max_steps is not None else train_cfg["steps"])
    requested = args.device or train_cfg.get("device")
    if requested in (None, "auto"):
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(requested)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    writer = RunWriter(
        stage_dir=REPO_ROOT / args.out,
        config=config,
        config_path=args.config,
        seed=seed,
        command="python -m des_ml.train.train_chunk_scorer " + " ".join(sys.argv[1:]),
        repo_root=REPO_ROOT,
        tags={
            "stage": "stage2",
            "kind": "chunk-scorer",
            "rounds": int(config["rounds"]),
            "mode": str(config["mode"]),
        },
    )
    model = ChunkScorer(
        hidden=int(config.get("model", {}).get("hidden", 256)),
        dropout=float(config.get("model", {}).get("dropout", 0.1)),
        sbox_lut=sbox_lut(),
        log_ddt=log_ddt_tensor(),
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(train_cfg.get("lr", 1e-3)),
        weight_decay=float(train_cfg.get("weight_decay", 1e-2)),
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(steps, 1))
    generator = torch.Generator(device=device)
    generator.manual_seed(seed)
    eval_generator = torch.Generator(device=device)
    eval_generator.manual_seed(seed + 1_000_003)

    log_every = int(train_cfg.get("log_every", 50))
    eval_every = int(train_cfg.get("eval_every", 250))
    best_acc = -math.inf
    best_metrics: dict[str, float] = {}
    final_metrics: dict[str, float] = {}
    try:
        model.train()
        for step in range(1, steps + 1):
            p1, p2, c1, c2, truth = make_batch(
                config,
                split=SPLIT_TRAIN,
                device=device,
                generator=generator,
                n_keys=int(train_cfg.get("keys_per_batch", 16)),
                pairs=int(train_cfg.get("pairs_per_key", 32)),
            )
            per_pair = model(p1, p2, c1, c2, return_per_pair=True)
            logits = per_pair.sum(dim=1)
            loss_listwise = F.cross_entropy(logits.reshape(-1, 64), truth.reshape(-1))
            expanded_truth = truth.unsqueeze(1).expand(-1, per_pair.shape[1], -1)
            loss_pair = F.cross_entropy(
                per_pair.reshape(-1, 64), expanded_truth.reshape(-1)
            )
            loss = loss_listwise + 0.5 * loss_pair
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()

            if step % log_every == 0 or step == 1:
                writer.log(
                    f"step={step} loss={loss.item():.6f} listwise={loss_listwise.item():.6f} "
                    f"pair={loss_pair.item():.6f} lr={scheduler.get_last_lr()[0]:.2e}"
                )
                print(
                    f"step={step} loss={loss.item():.6f} listwise={loss_listwise.item():.6f} "
                    f"pair={loss_pair.item():.6f}",
                    flush=True,
                )
            if step % eval_every == 0 or step == steps:
                metrics = evaluate(model, config, device=device, generator=eval_generator)
                metrics["train_loss"] = float(loss.item())
                writer.record(step, metrics)
                message = (
                    f"eval step={step} model_acc={metrics['model_acc']:.4f} "
                    f"model_rank={metrics['model_mean_rank']:.2f} "
                    f"ddt_acc={metrics['ddt_acc']:.4f} ddt_rank={metrics['ddt_mean_rank']:.2f}"
                )
                writer.log(message)
                print(message, flush=True)
                final_metrics = metrics
                if metrics["model_acc"] > best_acc:
                    best_acc = metrics["model_acc"]
                    best_metrics = metrics
                    if not args.no_checkpoint:
                        torch.save(
                            {
                                "model": model.state_dict(),
                                "config": config,
                                "step": step,
                                "metrics": metrics,
                            },
                            writer.path / "best.pt",
                        )
        final = dict(final_metrics)
        final["best_model_acc"] = best_acc
        manifest = writer.finish(status="completed", final=final)
        update_latest(REPO_ROOT / "results", writer.path, manifest)
        print(json.dumps({"run_dir": str(writer.path), "best": best_metrics, "final": final}, indent=2))
        return 0
    except Exception as exc:  # pragma: no cover - CI/failed runs
        writer.log(f"FAILED: {type(exc).__name__}: {exc}")
        writer.finish(status="failed", final=final_metrics, extra={"error": str(exc)})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
