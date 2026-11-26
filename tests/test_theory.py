import math

import numpy as np
import pytest

from des_ml.des import sbox_output
from des_ml.theory.ddt import (
    ddt_tables,
    lat_tables,
    log_ddt,
    max_ddt_entry,
    max_lat_abs,
)

DDT = ddt_tables()
LAT = lat_tables()


def test_ddt_row_sums_and_zero_difference():
    assert DDT.shape == (8, 64, 16)
    for j in range(8):
        assert int(DDT[j, 0, 0]) == 64
        assert int(DDT[j, 0, 1:].sum()) == 0
        assert np.all(DDT[j].sum(axis=1) == 64)
        assert np.all(DDT[j] >= 0)


def test_ddt_matches_the_sbox_definition():
    # A handful of entries recomputed directly from the table.
    for j in (0, 3, 7):
        for a in (0, 1, 0x15, 0x3F):
            counts = {}
            for x in range(64):
                b = sbox_output(j, x) ^ sbox_output(j, x ^ a)
                counts[b] = counts.get(b, 0) + 1
            for b in range(16):
                assert int(DDT[j, a, b]) == counts.get(b, 0)


def test_lat_constant_row_and_parity():
    assert LAT.shape == (8, 64, 16)
    for j in range(8):
        assert int(LAT[j, 0, 0]) == 64
        assert np.all(LAT[j, 0, 1:] == 0)
        # 64 terms of +-1 always sum to an even integer.
        assert np.all(LAT[j] % 2 == 0)
        # For a = 0 the transform is the S-box balance: 64^2 total energy.
        assert int((LAT[j, 0].astype(np.int64) ** 2).sum()) == 64 * 64


def test_maximum_entries_are_in_range():
    assert 1 <= max_ddt_entry(DDT) <= 64
    assert 1 <= max_lat_abs(LAT) <= 64


def test_log_ddt_floor_and_monotonicity():
    assert log_ddt(DDT[0], 0, 0) == pytest.approx(0.0)  # log(64/64)
    assert log_ddt(DDT[0], 0, 1) == pytest.approx(math.log(2.0**-8))
    high = log_ddt(DDT[0], 0x15, int(np.argmax(DDT[0, 0x15])))
    low = log_ddt(DDT[0], 0x15, int(np.argmin(DDT[0, 0x15])))
    assert high >= low
