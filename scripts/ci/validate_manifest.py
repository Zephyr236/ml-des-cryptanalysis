#!/usr/bin/env python3
"""Validate a single result directory (used by the CI smoke job)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from des_ml.manifest import validate_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()

    manifest_path = args.run_dir / "manifest.json"
    config_path = args.run_dir / "config.yaml"
    if not manifest_path.exists():
        print(f"missing {manifest_path}", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config_bytes = config_path.read_bytes() if config_path.exists() else None
    problems = validate_manifest(manifest, config_bytes=config_bytes)
    if problems:
        for problem in problems:
            print(f"::error::{problem}")
        return 1
    print(f"manifest ok: {manifest['run_id']} ({manifest['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
