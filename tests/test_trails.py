import math

import pytest

torch = pytest.importorskip("torch")

from des_ml.des import (
    IP,
    E,
    P,
    des_encrypt,
    des_encrypt_states,
    key_schedule,
    permute,
    sbox_output,
)
from des_ml.des_torch import des_encrypt_states_torch, rand64
from des_ml.theory.ddt import ddt_tables
from des_ml.theory.trails import (
    reconstruct,
    sbox_input_differences,
    search,
    shuffled_ddt,
    single_bit_starts,
)

MASK32 = 0xFFFFFFFF
MASK64 = (1 << 64) - 1
KEY = 0x133457799BBCDFF1
PLAINTEXT = 0x0123456789ABCDEF
DDT = ddt_tables()


def test_state_oracle_matches_cipher():
    for rounds in (1, 2, 4, 8, 16):
        states = des_encrypt_states(PLAINTEXT, KEY, rounds)
        assert len(states) == rounds + 1
        state = permute(des_encrypt(PLAINTEXT, KEY, rounds), IP, 64)
        # IP(C) = R_r || L_r; the oracle returns (L_r, R_r).
        assert states[-1] == (state & MASK32, (state >> 32) & MASK32)


def test_torch_state_oracle_matches_reference():
    generator = torch.Generator().manual_seed(3)
    blocks = rand64(16, generator=generator)
    keys = rand64(16, generator=generator)
    for rounds in (1, 2, 4, 8):
        torch_states = des_encrypt_states_torch(blocks, keys, rounds)
        for row in range(16):
            reference = des_encrypt_states(
                int(blocks[row]) & MASK64, int(keys[row]) & MASK64, rounds
            )
            for index in range(rounds + 1):
                left, right = torch_states[index]
                assert int(left[row]) & MASK32 == reference[index][0]
                assert int(right[row]) & MASK32 == reference[index][1]


def test_round_transition_algebra():
    other = PLAINTEXT ^ 0x0F0F0F0F0F0F0F0F
    rounds = 4
    states1 = des_encrypt_states(PLAINTEXT, KEY, rounds)
    states2 = des_encrypt_states(other, KEY, rounds)
    left1, right1 = states1[0]
    left2, right2 = states2[0]
    left_difference = left1 ^ left2
    right_difference = right1 ^ right2
    inputs = sbox_input_differences(right_difference)

    round_key = key_schedule(KEY, rounds)[0]
    expanded1 = permute(right1, E, 32)
    expanded2 = permute(right2, E, 32)
    outputs = []
    for j in range(8):
        shift = 42 - 6 * j
        assert inputs[j] == ((expanded1 >> shift) & 0x3F) ^ ((expanded2 >> shift) & 0x3F)
        chunk = (round_key >> shift) & 0x3F
        first = sbox_output(j, ((expanded1 >> shift) & 0x3F) ^ chunk)
        second = sbox_output(j, ((expanded2 >> shift) & 0x3F) ^ chunk)
        outputs.append(first ^ second)
    pre_p = 0
    for output in outputs:
        pre_p = (pre_p << 4) | output
    f_difference = permute(pre_p, P, 32)
    predicted_next = (right_difference, (left_difference ^ f_difference) & MASK32)
    actual_next = (
        (states1[1][0] ^ states2[1][0]) & MASK32,
        (states1[1][1] ^ states2[1][1]) & MASK32,
    )
    assert predicted_next == actual_next


def test_search_one_round_matches_ddt_maximum():
    right = 1 << 0
    expected = 0.0
    for j, difference in enumerate(sbox_input_differences(right)):
        if difference:
            expected += math.log2(int(DDT[j, difference].max()) / 64.0)
    _, best_active = search([(0, right)], 1, beam=50, branch=16, combos=64)
    assert 1 in best_active
    trail = reconstruct(best_active[1])
    assert trail.log2_probability == pytest.approx(expected)
    assert any(step.sbox_inputs for step in trail.steps)


def test_input_difference_roundtrip():
    _, best_active = search(single_bit_starts(), 2, beam=200, branch=4, combos=12)
    trail = reconstruct(best_active[2])
    state = permute(trail.input_difference, IP, 64)
    assert ((state >> 32) & MASK32, state & MASK32) == trail.start


def test_single_bit_starts_are_unique():
    starts = single_bit_starts()
    assert len(starts) == 64
    assert len(set(starts)) == 64


def test_shuffled_ddt_control_preserves_rows():
    import numpy as np

    ddt = ddt_tables()
    control = shuffled_ddt(7)
    assert control.shape == ddt.shape
    assert np.array_equal(control[:, 0, :], ddt[:, 0, :])
    assert np.array_equal(control.sum(axis=2), ddt.sum(axis=2))
    assert not np.array_equal(control, ddt)
    assert np.array_equal(control, shuffled_ddt(7))
