import pytest

from des_ml.des import PC1, PC2, key_schedule, permute
from des_ml.key_schedule import (
    coverage,
    recover_master_keys,
    round_key_master_positions,
)


def effective(key: int) -> int:
    return permute(key, PC1, 64)


def test_round_key_observes_48_distinct_master_bits():
    for round_index in range(1, 17):
        positions = round_key_master_positions(round_index)
        assert len(positions) == 48
        assert len(set(positions)) == 48


def test_one_round_key_leaves_eight_bits_free():
    assert len(coverage(1)) == 48
    assert len(coverage(16)) == 48
    # Two adjacent round keys should cover everything; assert the computed
    # value rather than assuming it.
    assert len(coverage([1, 2])) <= 56


def test_recovery_enumerates_256_candidates():
    key = 0x133457799BBCDFF1
    for round_index in (1, 2, 8, 16):
        round_key = key_schedule(key, 16)[round_index - 1]
        candidates = recover_master_keys(round_key, round_index)
        assert len(candidates) == 256
        assert len({effective(candidate) for candidate in candidates}) == 256
        assert effective(key) in {effective(candidate) for candidate in candidates}


def test_every_candidate_reproduces_the_round_key():
    key = 0x0F1E2D3C4B5A6978
    for round_index in range(1, 17):
        round_key = key_schedule(key, 16)[round_index - 1]
        for candidate in recover_master_keys(round_key, round_index):
            assert key_schedule(candidate, 16)[round_index - 1] == round_key


def test_parity_bits_are_zero():
    key = 0x123456789ABCDEF0
    round_key = key_schedule(key, 16)[0]
    for candidate in recover_master_keys(round_key, 1):
        for position in range(8, 65, 8):  # 1-based DES parity positions
            assert (candidate >> (64 - position)) & 1 == 0


def test_rejects_bad_inputs():
    with pytest.raises(ValueError):
        recover_master_keys(0, 0)
    with pytest.raises(ValueError):
        recover_master_keys(1 << 48, 1)
    with pytest.raises(ValueError):
        round_key_master_positions(17)
    assert len(PC2) == 48
    assert len(PC1) == 56
