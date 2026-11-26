#!/usr/bin/env python3
"""TH-1 (partial): exact DDT/LAT tables and key-schedule coverage.

Produces a committed artefact under ``results/stage1`` with:

* the eight 64x16 DDT tables and the eight 64x16 LAT tables;
* the per-round master-bit coverage map and the cumulative coverage;
* the 2^8 master-key completion check, verified by re-deriving the
  round key from every recovered candidate.

This is the classical ceiling that the SPADE residual is measured
against; it makes no neural claim.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from des_ml.des import PC1, key_schedule, permute  # noqa: E402
from des_ml.key_schedule import coverage, recover_master_keys  # noqa: E402
from des_ml.manifest import RunWriter, update_latest  # noqa: E402
from des_ml.theory.ddt import ddt_tables, lat_tables  # noqa: E402


def main() -> int:
    config = {
        "suite": "theory-core",
        "version": 1,
        "sboxes": 8,
        "ddt_shape": [64, 16],
        "lat_shape": [64, 16],
        "rounds": list(range(1, 17)),
        "recovery_keys": 16,
    }
    writer = RunWriter(
        stage_dir=REPO_ROOT / "results/stage1",
        config=config,
        config_path="scripts/theory_report.py",
        seed=0,
        command="python scripts/theory_report.py",
        repo_root=REPO_ROOT,
        tags={"stage": "stage1", "kind": "theory", "suite": "th-1-partial"},
    )

    ddt = ddt_tables()
    lat = lat_tables()
    tables_dir = writer.path / "tables"
    tables_dir.mkdir()

    (tables_dir / "ddt.json").write_text(
        json.dumps({str(j): ddt[j].tolist() for j in range(8)}), encoding="utf-8"
    )
    (tables_dir / "lat.json").write_text(
        json.dumps({str(j): lat[j].tolist() for j in range(8)}), encoding="utf-8"
    )

    round_maps = {}
    cumulative = set()
    for round_index in range(1, 17):
        observed = set(coverage(round_index))
        cumulative |= observed
        round_maps[str(round_index)] = {
            "observed_bits": len(observed),
            "cumulative_bits": len(cumulative),
            "positions": sorted(observed),
        }
    (tables_dir / "key_schedule_coverage.json").write_text(
        json.dumps(round_maps, indent=2), encoding="utf-8"
    )

    rng = random.Random(0)
    keys = [rng.getrandbits(64) for _ in range(config["recovery_keys"])]
    recovery_pass = True
    completion_counts = set()
    for key in keys:
        effective = permute(key, PC1, 64)
        for round_index in (1, 2, 4, 8, 16):
            round_key = key_schedule(key, 16)[round_index - 1]
            candidates = recover_master_keys(round_key, round_index)
            completion_counts.add(len(candidates))
            recovery_pass &= effective in {permute(c, PC1, 64) for c in candidates}
            recovery_pass &= all(
                key_schedule(candidate, 16)[round_index - 1] == round_key
                for candidate in candidates
            )

    ddt_rows_ok = bool(np.all(ddt.sum(axis=2) == 64))
    # A balanced S-box has a trivial a=0 row: LAT(0,0)=64 and zero elsewhere.
    lat_balance_ok = bool(
        all(int(lat[j, 0, 0]) == 64 and not np.any(lat[j, 0, 1:]) for j in range(8))
    )

    metrics = {
        "ddt_row_sums_ok": float(ddt_rows_ok),
        "lat_balance_ok": float(lat_balance_ok),
        # Exclude the trivial a=0 row; these are the meaningful bounds.
        "max_ddt_entry_nonzero": float(ddt[:, 1:, :].max()),
        "max_lat_abs_nontrivial": float(np.abs(lat[:, 1:, :]).max()),
        "differential_uniformity": float(ddt[:, 1:, :].max()) / 64.0,
        "max_linear_correlation": float(np.abs(lat[:, 1:, :]).max()) / 64.0,
        "coverage_round1": float(len(coverage(1))),
        "coverage_rounds_1_2": float(len(coverage([1, 2]))),
        "coverage_all_rounds": float(len(coverage(list(range(1, 17))))),
        "completions_per_round_key": float(max(completion_counts)),
        "recovery_pass": float(recovery_pass),
        "keys_checked": float(len(keys)),
    }
    writer.log(json.dumps(metrics, indent=2, sort_keys=True))
    writer.record(0, metrics)
    manifest = writer.finish(status="completed", final=metrics)
    update_latest(REPO_ROOT / "results", writer.path, manifest)
    print(json.dumps({"run_dir": str(writer.path), "metrics": metrics}, indent=2))

    required = ("ddt_row_sums_ok", "lat_balance_ok", "recovery_pass")
    return 0 if all(metrics[name] == 1.0 for name in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
