import pytest

from des_ml.des import des_decrypt, des_encrypt, key_schedule

# FIPS PUB 46-3 / NIST example vector.
FIPS_KEY = 0x133457799BBCDFF1
FIPS_PLAINTEXT = 0x0123456789ABCDEF
FIPS_CIPHERTEXT = 0x85E813540F0AB405


def test_fips_vector():
    assert des_encrypt(FIPS_PLAINTEXT, FIPS_KEY) == FIPS_CIPHERTEXT
    assert des_decrypt(FIPS_CIPHERTEXT, FIPS_KEY) == FIPS_PLAINTEXT


@pytest.mark.parametrize("rounds", range(1, 17))
def test_roundtrip_every_round_count(rounds):
    ciphertext = des_encrypt(FIPS_PLAINTEXT, FIPS_KEY, rounds)
    assert des_decrypt(ciphertext, FIPS_KEY, rounds) == FIPS_PLAINTEXT


def test_round_reduced_differs_from_full():
    assert des_encrypt(FIPS_PLAINTEXT, FIPS_KEY, 4) != FIPS_CIPHERTEXT
    assert des_encrypt(FIPS_PLAINTEXT, FIPS_KEY, 16) == FIPS_CIPHERTEXT


def test_parity_bits_are_ignored():
    # DES key bits 8, 16, ..., 64 are parity bits -> integer bits 56, 48, ..., 0.
    for integer_bit in range(0, 64, 8):
        flipped = FIPS_KEY ^ (1 << integer_bit)
        assert des_encrypt(FIPS_PLAINTEXT, flipped) == FIPS_CIPHERTEXT


def test_key_schedule_shape_and_range():
    subkeys = key_schedule(FIPS_KEY)
    assert len(subkeys) == 16
    assert all(0 <= key < (1 << 48) for key in subkeys)
    assert len(set(subkeys)) == 16


def test_rejects_bad_inputs():
    with pytest.raises(ValueError):
        key_schedule(FIPS_KEY, 0)
    with pytest.raises(ValueError):
        key_schedule(FIPS_KEY, 17)
    with pytest.raises(ValueError):
        des_encrypt(1 << 64, FIPS_KEY)
    with pytest.raises(ValueError):
        des_encrypt(0, 1 << 64)
