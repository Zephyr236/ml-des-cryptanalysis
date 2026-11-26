import pytest

torch = pytest.importorskip("torch")

from des_ml.data import SPLIT_TEST, SPLIT_TRAIN, SPLIT_VAL, PairStream, key_split, split_of
from des_ml.des_torch import des_encrypt_torch, effective_key_torch, rand64


def test_split_is_deterministic_and_parity_invariant():
    generator = torch.Generator().manual_seed(3)
    keys = rand64(256, generator=generator)
    assert torch.equal(split_of(keys), split_of(keys))
    # Integer bits 0, 8, ..., 56 are DES parity bits.
    for bit in range(0, 64, 8):
        assert torch.equal(split_of(keys ^ (1 << bit)), split_of(keys))


def _reference_bucket(effective_key: int) -> int:
    mask = (1 << 64) - 1
    h = (effective_key ^ 0x5EED5EED5EED5E) & mask
    h ^= h >> 30
    h = (h * 0xBF58476D1CE4E5B9) & mask
    h ^= h >> 27
    h = (h * 0x94D049BB133111EB) & mask
    h ^= h >> 31
    return (h & 0x7FFFFFFFFFFFFFFF) % 100


def test_split_matches_reference_splitmix64():
    generator = torch.Generator().manual_seed(99)
    keys = rand64(64, generator=generator)
    effective = effective_key_torch(keys)
    expected = torch.tensor(
        [_reference_bucket(int(value)) for value in effective], dtype=torch.long
    )
    assert torch.equal(key_split(keys), expected)


def test_split_is_approximately_80_10_10():
    generator = torch.Generator().manual_seed(4)
    keys = rand64(50_000, generator=generator)
    splits = split_of(keys)
    train = float((splits == SPLIT_TRAIN).float().mean())
    val = float((splits == SPLIT_VAL).float().mean())
    test = float((splits == SPLIT_TEST).float().mean())
    assert abs(train - 0.80) < 0.02
    assert abs(val - 0.10) < 0.01
    assert abs(test - 0.10) < 0.01


def test_kpa_stream_contract():
    stream = PairStream(rounds=2, mode="kpa", split=SPLIT_TRAIN, batch_size=64, seed=11)
    batch = stream.batch()
    assert batch.plaintext1.shape == (64,)
    assert batch.labels.shape == (64,)
    assert set(batch.labels.tolist()) <= {0, 1}

    positive = batch.labels.bool()
    expected = des_encrypt_torch(
        batch.plaintext1[positive], batch.keys[positive], 2
    )
    assert torch.equal(batch.ciphertext1[positive], expected)

    planes = batch.to_planes()
    assert planes.shape == (64, 6, 64)
    assert planes.min() >= -1.0 and planes.max() <= 1.0


def test_cpa_stream_uses_fixed_delta():
    delta = 0x0F0F0F0F0F0F0F0F
    stream = PairStream(
        rounds=2, mode="cpa", split=SPLIT_VAL, batch_size=32, seed=5, delta=delta
    )
    batch = stream.batch()
    assert torch.equal(batch.plaintext2, batch.plaintext1 ^ delta)


def test_cpa_requires_delta():
    with pytest.raises(ValueError):
        PairStream(rounds=2, mode="cpa", split=SPLIT_TRAIN, batch_size=8, delta=None)


def test_all_negative_stream_has_no_cipher_signal():
    stream = PairStream(
        rounds=4,
        mode="kpa",
        split=SPLIT_TEST,
        batch_size=16,
        seed=6,
        negative_fraction=1.0,
    )
    batch = stream.batch()
    assert bool((batch.labels == 0).all())
