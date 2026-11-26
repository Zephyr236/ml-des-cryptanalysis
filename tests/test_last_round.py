import pytest

from des_ml.des import IP, des_encrypt, key_schedule, permute
from des_ml.last_round import (
    apply_chunk,
    chunk_bits,
    chunk_ddt_score,
    chunk_positions,
    last_round_words,
    previous_state,
    sbox_input,
    true_chunk_key,
)
from des_ml.theory.ddt import ddt_tables

DDT = ddt_tables()
KEY = 0x133457799BBCDFF1
PLAINTEXT = 0x0123456789ABCDEF


@pytest.mark.parametrize("rounds", range(1, 17))
def test_true_chunk_reproduces_the_four_previous_state_bits(rounds):
    ciphertext = des_encrypt(PLAINTEXT, KEY, rounds)
    right_r, left_r = last_round_words(ciphertext)
    _, left_previous = previous_state(PLAINTEXT, KEY, rounds)
    for sbox_index in range(8):
        candidate = true_chunk_key(KEY, rounds, sbox_index)
        bits = chunk_bits(right_r, left_r, candidate, sbox_index)
        expected = tuple(
            (left_previous >> (31 - position)) & 1
            for position in chunk_positions(sbox_index)
        )
        assert bits == expected


def test_previous_state_matches_the_real_cipher():
    for rounds in range(1, 17):
        right_previous, left_previous = previous_state(PLAINTEXT, KEY, rounds)
        block = PLAINTEXT if rounds == 1 else des_encrypt(PLAINTEXT, KEY, rounds - 1)
        state = permute(block, IP, 64)
        if rounds == 1:
            # IP(P) = L_0 || R_0 (no final swap at round zero).
            assert right_previous == state & 0xFFFFFFFF
            assert left_previous == (state >> 32) & 0xFFFFFFFF
        else:
            assert right_previous == (state >> 32) & 0xFFFFFFFF
            assert left_previous == state & 0xFFFFFFFF


def test_chunk_positions_partition_the_output():
    seen = set()
    for sbox_index in range(8):
        positions = chunk_positions(sbox_index)
        assert len(positions) == 4
        assert len(set(positions)) == 4
        assert not seen.intersection(positions)
        seen.update(positions)
    assert seen == set(range(32))


def test_sbox_input_is_six_bits():
    for sbox_index in range(8):
        assert 0 <= sbox_input(0xDEADBEEF, sbox_index) < 64


def test_ddt_score_is_pair_symmetric():
    ciphertext1 = des_encrypt(PLAINTEXT, KEY, 6)
    ciphertext2 = des_encrypt(PLAINTEXT ^ 0x0F0F0F0F0F0F0F0F, KEY, 6)
    for sbox_index in range(8):
        for candidate in (0, 17, 63):
            forward = chunk_ddt_score(ciphertext1, ciphertext2, candidate, sbox_index, DDT[sbox_index])
            backward = chunk_ddt_score(ciphertext2, ciphertext1, candidate, sbox_index, DDT[sbox_index])
            assert forward == pytest.approx(backward)


def test_apply_chunk_only_changes_its_four_bits():
    ciphertext = des_encrypt(PLAINTEXT, KEY, 4)
    right_r, left_r = last_round_words(ciphertext)
    base = apply_chunk(right_r, left_r, 0, 3)
    other = apply_chunk(right_r, left_r, 63, 3)
    positions = set(chunk_positions(3))
    differing = {
        bit for bit in range(32) if ((base >> (31 - bit)) & 1) != ((other >> (31 - bit)) & 1)
    }
    assert differing <= positions


def test_round_key_slice_matches_true_chunk():
    round_key = key_schedule(KEY, 6)[-1]
    for sbox_index in range(8):
        expected = (round_key >> (42 - 6 * sbox_index)) & 0x3F
        assert true_chunk_key(KEY, 6, sbox_index) == expected
