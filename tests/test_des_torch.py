import pytest

torch = pytest.importorskip("torch")

from des_ml.des import des_decrypt, des_encrypt
from des_ml.des_torch import (
    des_decrypt_torch,
    des_encrypt_torch,
    effective_key_torch,
    rand64,
)

ROUNDS = [1, 2, 4, 6, 8, 10, 12, 14, 16]
MASK64 = (1 << 64) - 1


def to_signed(value: int) -> int:
    """Reinterpret a 64-bit pattern as a signed int64 (torch's storage type)."""
    return value - (1 << 64) if value >= (1 << 63) else value


@pytest.fixture(scope="module")
def samples():
    generator = torch.Generator().manual_seed(1234)
    plaintexts = rand64(64, generator=generator)
    keys = rand64(64, generator=generator)
    return plaintexts, keys


@pytest.mark.parametrize("rounds", ROUNDS)
def test_matches_reference(samples, rounds):
    plaintexts, keys = samples
    expected = torch.tensor(
        [
            to_signed(des_encrypt(int(p) & MASK64, int(k) & MASK64, rounds))
            for p, k in zip(plaintexts, keys, strict=True)
        ],
        dtype=torch.long,
    )
    actual = des_encrypt_torch(plaintexts, keys, rounds)
    assert torch.equal(actual, expected)


@pytest.mark.parametrize("rounds", ROUNDS)
def test_decrypt_matches_reference(samples, rounds):
    plaintexts, keys = samples
    ciphertexts = des_encrypt_torch(plaintexts, keys, rounds)
    expected = torch.tensor(
        [
            to_signed(des_decrypt(int(c) & MASK64, int(k) & MASK64, rounds))
            for c, k in zip(ciphertexts, keys, strict=True)
        ],
        dtype=torch.long,
    )
    assert torch.equal(des_decrypt_torch(ciphertexts, keys, rounds), expected)
    assert torch.equal(des_decrypt_torch(ciphertexts, keys, rounds), plaintexts)


def test_scalar_key_broadcast(samples):
    plaintexts, keys = samples
    key = int(keys[0])
    expected = des_encrypt_torch(plaintexts, keys[0])
    actual = des_encrypt_torch(plaintexts, key)
    assert torch.equal(actual, expected)


def test_effective_key_is_56_bits(samples):
    _, keys = samples
    effective = effective_key_torch(keys)
    assert int(effective.max()) < (1 << 56)
    # Flipping a parity bit must not change the effective key.
    parity_flipped = keys ^ 1  # integer bit 0 is DES parity bit 64
    assert torch.equal(effective_key_torch(parity_flipped), effective)


def test_rand64_covers_full_64_bit_patterns():
    generator = torch.Generator().manual_seed(7)
    values = rand64(4096, generator=generator)
    assert values.dtype == torch.int64
    # Signed int64 is used as a 64-bit pattern container: both halves must vary.
    high = (values >> 32) & 0xFFFFFFFF
    low = values & 0xFFFFFFFF
    assert int(high.min()) >= 0 and int(high.max()) < (1 << 32)
    assert int(low.min()) >= 0 and int(low.max()) < (1 << 32)
    assert int(values.min()) < 0 < int(values.max())
