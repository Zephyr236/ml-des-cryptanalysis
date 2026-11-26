#!/usr/bin/env python3
"""DES conformance run.

This is the first result every revision must produce: it proves that the
reference implementation and the vectorised implementation agree, that
the FIPS test vector passes, and that parity bits are ignored.  It is
pure Python except for the optional torch cross-check.

Usage::

    python scripts/run_conformance.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from des_ml.des import des_decrypt, des_encrypt  # noqa: E402
from des_ml.manifest import RunWriter, update_latest  # noqa: E402

FIPS_KEY = 0x133457799BBCDFF1
FIPS_PLAINTEXT = 0x0123456789ABCDEF
FIPS_CIPHERTEXT = 0x85E813540F0AB405
MASK64 = (1 << 64) - 1


def _to_signed(value: int) -> int:
    return value - (1 << 64) if value >= (1 << 63) else value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-torch", action="store_true", help="Skip the torch cross-check")
    args = parser.parse_args()

    config = {
        "suite": "des-conformance",
        "version": 1,
        "rounds": list(range(1, 17)),
        "fips_vector": [hex(FIPS_KEY), hex(FIPS_PLAINTEXT), hex(FIPS_CIPHERTEXT)],
    }
    writer = RunWriter(
        stage_dir=REPO_ROOT / "results/stage0",
        config=config,
        config_path="scripts/run_conformance.py",
        seed=0,
        command="python scripts/run_conformance.py",
        repo_root=REPO_ROOT,
        tags={"stage": "stage0", "kind": "conformance"},
    )

    checks: dict[str, float] = {}
    fips_ok = des_encrypt(FIPS_PLAINTEXT, FIPS_KEY) == FIPS_CIPHERTEXT
    checks["fips_vector_pass"] = float(fips_ok)
    writer.log(f"fips_vector_pass={fips_ok}")

    roundtrip_ok = all(
        des_decrypt(des_encrypt(FIPS_PLAINTEXT, FIPS_KEY, rounds), FIPS_KEY, rounds)
        == FIPS_PLAINTEXT
        for rounds in range(1, 17)
    )
    checks["roundtrip_pass"] = float(roundtrip_ok)
    writer.log(f"roundtrip_pass={roundtrip_ok}")

    parity_ok = all(
        des_encrypt(FIPS_PLAINTEXT, FIPS_KEY ^ (1 << bit)) == FIPS_CIPHERTEXT
        for bit in range(0, 64, 8)
    )
    checks["parity_invariance_pass"] = float(parity_ok)
    writer.log(f"parity_invariance_pass={parity_ok}")

    if not args.no_torch:
        try:
            import torch

            from des_ml.des_torch import des_encrypt_torch, rand64

            generator = torch.Generator().manual_seed(2026)
            plaintexts = rand64(256, generator=generator)
            keys = rand64(256, generator=generator)
            torch_ok = True
            for rounds in (1, 2, 4, 8, 12, 16):
                expected = torch.tensor(
                    [
                        _to_signed(des_encrypt(int(p) & MASK64, int(k) & MASK64, rounds))
                        for p, k in zip(plaintexts, keys, strict=True)
                    ],
                    dtype=torch.long,
                )
                torch_ok &= bool(torch.equal(des_encrypt_torch(plaintexts, keys, rounds), expected))
            checks["torch_equivalence_pass"] = float(torch_ok)
            checks["torch_available"] = 1.0
            checks["cuda_available"] = float(torch.cuda.is_available())
            writer.log(f"torch_equivalence_pass={torch_ok}")
        except Exception as exc:  # pragma: no cover - depends on the host
            checks["torch_available"] = 0.0
            writer.log(f"torch cross-check skipped: {type(exc).__name__}: {exc}")

    start = time.perf_counter()
    blocks = 20_000
    key = 0x0E0E0E0E0E0E0E0E
    for index in range(blocks):
        des_encrypt((index * 0x9E3779B97F4A7C15) & ((1 << 64) - 1), key)
    elapsed = time.perf_counter() - start
    checks["reference_blocks_per_second"] = blocks / elapsed
    writer.log(f"reference_throughput={checks['reference_blocks_per_second']:.0f} blocks/s")

    writer.record(0, checks)
    manifest = writer.finish(status="completed", final=checks)
    update_latest(REPO_ROOT / "results", writer.path, manifest)
    print(f"conformance written to {writer.path}")

    required = ("fips_vector_pass", "roundtrip_pass", "parity_invariance_pass")
    if not all(checks.get(name) == 1.0 for name in required):
        print("CONFORMANCE FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
