#!/usr/bin/env python3
"""TH-1: beam-search differential trails and validate them on the cipher.

    python scripts/trail_search.py --config configs/theory/trail-search.yaml

The search returns a valid trail (a lower bound on the best characteristic)
and a Monte Carlo estimate of the probability that a sampled pair with the
trail's input difference follows the full state-difference path.  See
ADR-0009.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import torch
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from des_ml.des_torch import des_encrypt_states_torch, rand64  # noqa: E402
from des_ml.manifest import RunWriter, update_latest  # noqa: E402
from des_ml.theory.trails import (  # noqa: E402
    Trail,
    multi_bit_starts,
    reconstruct,
    search,
    shuffled_ddt,
    single_bit_starts,
)

MASK32 = 0xFFFFFFFF


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", default="results/stage1")
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-rounds", type=int, default=None)
    parser.add_argument("--beam", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args()


def trail_to_dict(trail: Trail) -> dict:
    return {
        "rounds": len(trail.steps),
        "log2_probability": trail.log2_probability,
        "probability": trail.probability,
        "input_difference": f"0x{trail.input_difference:016X}",
        "states": [[f"0x{left:08X}", f"0x{right:08X}"] for left, right in trail.states],
        "steps": [
            {
                "left_in": f"0x{step.left_in:08X}",
                "right_in": f"0x{step.right_in:08X}",
                "sbox_inputs": list(step.sbox_inputs),
                "sbox_outputs": list(step.sbox_outputs),
                "log2_probability": step.log2_probability,
            }
            for step in trail.steps
        ],
    }


def validate_trail(
    trail: Trail,
    *,
    samples: int,
    batch: int,
    device: torch.device,
    generator: torch.Generator,
) -> float:
    """Empirical frequency of the full state-difference path."""
    rounds = len(trail.steps)
    matches = 0
    for offset in range(0, samples, batch):
        n = min(batch, samples - offset)
        plaintext = rand64(n, device=device, generator=generator)
        delta = trail.input_difference
        if delta >= 1 << 63:
            delta -= 1 << 64  # int64 pattern for a top-bit difference
        other = plaintext ^ delta
        keys = rand64(n, device=device, generator=generator)
        states1 = des_encrypt_states_torch(plaintext, keys, rounds)
        states2 = des_encrypt_states_torch(other, keys, rounds)
        ok = torch.ones(n, dtype=torch.bool, device=device)
        for index in range(1, rounds + 1):
            left1, right1 = states1[index]
            left2, right2 = states2[index]
            ok &= ((left1 ^ left2) & MASK32) == trail.states[index][0]
            ok &= ((right1 ^ right2) & MASK32) == trail.states[index][1]
        matches += int(ok.sum().item())
    return matches / samples


def main() -> int:
    args = parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.max_rounds is not None:
        config["max_rounds"] = args.max_rounds
    if args.beam is not None:
        config["beam"] = args.beam
    if args.seed is not None:
        config["seed"] = args.seed

    device = torch.device(args.device or ("cuda" if torch.cuda.is_available() else "cpu"))
    seed = int(config.get("seed", 0))
    generator = torch.Generator(device=device)
    generator.manual_seed(seed)
    torch.manual_seed(seed)

    writer = RunWriter(
        stage_dir=REPO_ROOT / args.out,
        config=config,
        config_path=args.config,
        seed=seed,
        command="python scripts/trail_search.py " + " ".join(sys.argv[1:]),
        repo_root=REPO_ROOT,
        tags={"stage": "stage1", "kind": "trail-search"},
    )

    if config.get("starts", "single_bit") == "multi_bit":
        starts = multi_bit_starts(seed, int(config.get("random_starts", 256)))
    else:
        starts = single_bit_starts()
    max_rounds = int(config["max_rounds"])
    beam = int(config.get("beam", 2000))
    branch = int(config.get("branch", 4))
    combos = int(config.get("combos", 12))
    search_start = time.perf_counter()
    best, best_active, best_full_active = search(
        starts, max_rounds, beam=beam, branch=branch, combos=combos
    )
    search_seconds = time.perf_counter() - search_start

    payload = {
        "parameters": {
            "starts": len(starts),
            "max_rounds": max_rounds,
            "beam": beam,
            "branch": branch,
            "combos": combos,
            "seed": seed,
        },
        "sbox_indexing": (
            "0-based array index: index 0 is S1, index 1 is S2, ..., index 7 is S8"
        ),
        "best": {str(r): trail_to_dict(reconstruct(node)) for r, node in best.items()},
        "best_active": {
            str(r): trail_to_dict(reconstruct(node)) for r, node in best_active.items()
        },
        "best_full_active": {
            str(r): trail_to_dict(reconstruct(node)) for r, node in best_full_active.items()
        },
    }
    (writer.path / "trails.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    metrics: dict[str, float] = {
        "starts": float(len(starts)),
        "max_rounds": float(max_rounds),
        "beam": float(beam),
        "branch": float(branch),
        "combos": float(combos),
        "search_seconds": search_seconds,
        "device_is_cuda": float(device.type == "cuda"),
    }
    for r, node in best.items():
        trail = reconstruct(node)
        metrics[f"best_log2_probability_r{r}"] = trail.log2_probability
        metrics[f"best_probability_r{r}"] = trail.probability
    for r, node in best_active.items():
        trail = reconstruct(node)
        metrics[f"best_active_log2_probability_r{r}"] = trail.log2_probability
        metrics[f"best_active_probability_r{r}"] = trail.probability
    metrics["best_active_rounds"] = float(len(best_active))
    for r, node in best_full_active.items():
        trail = reconstruct(node)
        metrics[f"best_full_active_log2_probability_r{r}"] = trail.log2_probability
        metrics[f"best_full_active_probability_r{r}"] = trail.probability
    metrics["best_full_active_rounds"] = float(len(best_full_active))

    # Power analysis: a trail is only useful downstream when N*p gives
    # enough right pairs.  Record both the expected count at the current
    # 64-pairs/key budget and the pairs needed for 1/10/100 right pairs.
    for r, node in best_active.items():
        probability = reconstruct(node).probability
        metrics[f"power_r{r}_expected_at_64"] = 64.0 * probability
        for target in (1, 10, 100):
            metrics[f"power_r{r}_pairs_for_{target}"] = (
                math.ceil(target / probability) if probability > 0 else float("inf")
            )

    sensitivity: dict[str, dict[str, float]] = {}
    sensitivity_cfg = config.get("sensitivity") or {}
    sensitivity_beams = [int(value) for value in sensitivity_cfg.get("beams", [])]
    sensitivity_branches = [int(value) for value in sensitivity_cfg.get("branches", [])]
    sensitivity_combos = [int(value) for value in sensitivity_cfg.get("combos", [])]
    if sensitivity_beams or sensitivity_branches or sensitivity_combos:
        sensitivity_start = time.perf_counter()
        for sensitivity_beam in sensitivity_beams:
            _, active, _ = search(
                starts, max_rounds, beam=sensitivity_beam, branch=branch, combos=combos
            )
            entry = {str(r): reconstruct(node).log2_probability for r, node in active.items()}
            sensitivity[f"beam:{sensitivity_beam}"] = entry
            for r, node in active.items():
                metrics[f"sensitivity_beam{sensitivity_beam}_log2p_r{r}"] = (
                    reconstruct(node).log2_probability
                )
        for sensitivity_branch in sensitivity_branches:
            _, active, _ = search(
                starts, max_rounds, beam=beam, branch=sensitivity_branch, combos=combos
            )
            entry = {str(r): reconstruct(node).log2_probability for r, node in active.items()}
            sensitivity[f"branch:{sensitivity_branch}"] = entry
            for r, node in active.items():
                metrics[f"sensitivity_branch{sensitivity_branch}_log2p_r{r}"] = (
                    reconstruct(node).log2_probability
                )
        for sensitivity_combo in sensitivity_combos:
            _, active, _ = search(
                starts, max_rounds, beam=beam, branch=branch, combos=sensitivity_combo
            )
            entry = {str(r): reconstruct(node).log2_probability for r, node in active.items()}
            sensitivity[f"combos:{sensitivity_combo}"] = entry
            for r, node in active.items():
                metrics[f"sensitivity_combos{sensitivity_combo}_log2p_r{r}"] = (
                    reconstruct(node).log2_probability
                )
        metrics["sensitivity_seconds"] = time.perf_counter() - sensitivity_start
        (writer.path / "sensitivity.json").write_text(
            json.dumps(sensitivity, indent=2, sort_keys=True), encoding="utf-8"
        )

    control_cfg = config.get("controls") or {}
    if control_cfg.get("shuffled_ddt"):
        control_start = time.perf_counter()
        control_ddt = shuffled_ddt(int(control_cfg.get("seed", 7)))
        _, control_active, _ = search(
            starts,
            max_rounds,
            beam=beam,
            branch=branch,
            combos=combos,
            ddt=control_ddt,
        )
        control = {
            str(r): reconstruct(node).log2_probability for r, node in control_active.items()
        }
        for r, node in control_active.items():
            metrics[f"control_shuffled_ddt_log2p_r{r}"] = reconstruct(node).log2_probability
        metrics["control_seconds"] = time.perf_counter() - control_start
        (writer.path / "control.json").write_text(
            json.dumps(control, indent=2, sort_keys=True), encoding="utf-8"
        )

    validation = config.get("validation") or {}
    samples_cfg = validation.get("samples") or {}
    batch = int(validation.get("batch", 8192))
    all_passed = True
    validation_start = time.perf_counter()
    for round_key in validation.get("rounds", []):
        round_index = int(round_key)
        node = best_active.get(round_index)
        if node is None:
            continue
        trail = reconstruct(node)
        n = int(samples_cfg.get(round_key, samples_cfg.get(str(round_key), 0)))
        if n <= 0:
            continue
        empirical = validate_trail(
            trail, samples=n, batch=batch, device=device, generator=generator
        )
        predicted = trail.probability
        sigma = math.sqrt(max(predicted * (1.0 - predicted), 1e-12) / n)
        passed = empirical >= predicted - 3.0 * sigma
        all_passed &= passed
        z = 1.96
        denominator = 1.0 + z * z / n
        centre = (empirical + z * z / (2.0 * n)) / denominator
        half = (
            z
            * math.sqrt(empirical * (1.0 - empirical) / n + z * z / (4.0 * n * n))
            / denominator
        )
        metrics[f"validation_r{round_index}_samples"] = float(n)
        metrics[f"validation_r{round_index}_predicted"] = predicted
        metrics[f"validation_r{round_index}_empirical"] = empirical
        metrics[f"validation_r{round_index}_ci_low"] = max(0.0, centre - half)
        metrics[f"validation_r{round_index}_ci_high"] = min(1.0, centre + half)
        metrics[f"validation_r{round_index}_pass"] = float(passed)
        writer.log(
            f"validate r={round_index} predicted={predicted:.6g} "
            f"empirical={empirical:.6g} n={n} pass={passed}"
        )
    metrics["validation_seconds"] = time.perf_counter() - validation_start
    metrics["validation_all_pass"] = float(all_passed)

    writer.record(0, metrics)
    manifest = writer.finish(status="completed", final=metrics)
    update_latest(REPO_ROOT / "results", writer.path, manifest)
    print(json.dumps({"run_dir": str(writer.path), "metrics": metrics}, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
