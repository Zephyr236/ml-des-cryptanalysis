"""Difference and linear distribution tables for the DES S-boxes.

These are the exact classical statistics that every neural score is
compared against (ADR-0008).  Tables are small enough to compute on the
CPU and commit as artefacts.
"""

from __future__ import annotations

import math

import numpy as np

from des_ml.des import sbox_output

__all__ = [
    "ddt_tables",
    "lat_tables",
    "log_ddt",
    "max_ddt_entry",
    "max_lat_abs",
]

DDT_FLOOR = 2.0**-8


def ddt_tables() -> np.ndarray:
    """Return an ``(8, 64, 16)`` array of DDT counts.

    ``ddt[j, a, b]`` counts ``x`` with ``S_j(x) ^ S_j(x ^ a) == b``.
    """
    tables = np.zeros((8, 64, 16), dtype=np.int64)
    for j in range(8):
        for a in range(64):
            for x in range(64):
                output = sbox_output(j, x) ^ sbox_output(j, x ^ a)
                tables[j, a, output] += 1
    return tables


def lat_tables() -> np.ndarray:
    """Return an ``(8, 64, 16)`` array of linear-approximation values.

    ``lat[j, a, b] = sum_x (-1)^{a·x ^ b·S_j(x)}``.
    """
    tables = np.zeros((8, 64, 16), dtype=np.int64)
    for j in range(8):
        for a in range(64):
            for b in range(16):
                total = 0
                for x in range(64):
                    parity = bin(a & x).count("1") ^ bin(b & sbox_output(j, x)).count("1")
                    total += -1 if parity & 1 else 1
                tables[j, a, b] = total
    return tables


def log_ddt(ddt: np.ndarray, a: int, b: int, *, floor: float = DDT_FLOOR) -> float:
    """Log-likelihood of output difference ``b`` given input difference ``a``."""
    probability = float(ddt[a, b]) / 64.0
    return math.log(max(probability, floor))


def max_ddt_entry(ddt: np.ndarray) -> int:
    return int(ddt.max())


def max_lat_abs(lat: np.ndarray) -> int:
    return int(np.abs(lat).max())
