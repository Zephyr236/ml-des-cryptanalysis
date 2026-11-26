"""Synthetic data streams for round-reduced DES experiments.

Two threat models are supported:

``kpa``
    Known plaintext: plaintexts are uniform random; the attacker does
    not choose them.

``cpa``
    Chosen plaintext: plaintext pairs share a fixed difference
    ``delta`` drawn from the experiment configuration.

Every stream is *key-disjoint*: keys are partitioned into train / val /
test buckets by a deterministic hash of the 56-bit effective key, and a
stream only ever emits keys from its assigned bucket.  This is the
control that prevents memorisation of a key from being reported as
generalisation.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch

from .des_torch import des_encrypt_torch, effective_key_torch, rand64

__all__ = [
    "PairBatch",
    "PairStream",
    "key_split",
    "blocks_to_planes",
    "SPLIT_TRAIN",
    "SPLIT_VAL",
    "SPLIT_TEST",
    "SPLIT_VERSION",
]

SPLIT_TRAIN = 0
SPLIT_VAL = 1
SPLIT_TEST = 2

# Thresholds over the 0..99 hash bucket: 80 / 10 / 10 percent.
_SPLIT_EDGES = (80, 90)
SPLIT_VERSION = "splitmix64-v1"

# 56-bit salt; versioned together with the finalizer in ADR-0007.
_SPLIT_SALT = 0x5EED5EED5EED5E
# SplitMix64 finalizer multipliers as signed int64 (two's complement).
_MIX1 = -4658895280553007687  # 0xBF58476D1CE4E5B9
_MIX2 = -7723592293110705685  # 0x94D049BB133111EB


def _logical_shift_right(value: torch.Tensor, amount: int) -> torch.Tensor:
    """Logical (unsigned) right shift for signed int64 patterns."""
    return (value >> amount) & ((1 << (64 - amount)) - 1)


def key_split(keys: torch.Tensor) -> torch.Tensor:
    """Map 64-bit keys to a 0..99 bucket derived from the effective key.

    Keys that differ only in parity bits map to the same bucket, which
    is what we want: DES ignores those bits, so they must not create
    artificial train/test separation.

    The construction is SplitMix64 applied to the salted 56-bit
    effective key.  It is vectorised so that rejection sampling can run
    inside the GPU data stream; see ADR-0007.
    """
    h = effective_key_torch(keys) ^ _SPLIT_SALT
    h = h ^ _logical_shift_right(h, 30)
    h = h * _MIX1
    h = h ^ _logical_shift_right(h, 27)
    h = h * _MIX2
    h = h ^ _logical_shift_right(h, 31)
    h = h & 0x7FFFFFFFFFFFFFFF
    return h % 100


def split_of(keys: torch.Tensor) -> torch.Tensor:
    buckets = key_split(keys)
    # right=True gives boundaries 0..79 -> 0, 80..89 -> 1, 90..99 -> 2.
    return torch.bucketize(
        buckets, torch.tensor(_SPLIT_EDGES, device=keys.device), right=True
    )


def blocks_to_planes(blocks: torch.Tensor) -> torch.Tensor:
    """(B,) int64 blocks -> (B, 64) float32 bit planes, MSB first."""
    shifts = torch.arange(63, -1, -1, device=blocks.device)
    return ((blocks.unsqueeze(1) >> shifts) & 1).float()


@dataclass
class PairBatch:
    plaintext1: torch.Tensor
    plaintext2: torch.Tensor
    ciphertext1: torch.Tensor
    ciphertext2: torch.Tensor
    keys: torch.Tensor
    labels: torch.Tensor  # 1 = produced by the cipher, 0 = random permutation

    def to_planes(self) -> torch.Tensor:
        """Return the (B, 6, 64) input tensor used by the pair models."""
        p1 = blocks_to_planes(self.plaintext1)
        p2 = blocks_to_planes(self.plaintext2)
        c1 = blocks_to_planes(self.ciphertext1)
        c2 = blocks_to_planes(self.ciphertext2)
        return torch.stack((p1, p2, c1, c2, p1 - p2, c1 - c2), dim=1)

    def to(self, device: torch.device | str) -> PairBatch:
        return PairBatch(
            self.plaintext1.to(device),
            self.plaintext2.to(device),
            self.ciphertext1.to(device),
            self.ciphertext2.to(device),
            self.keys.to(device),
            self.labels.to(device),
        )


class PairStream:
    """Endless batch generator for a fixed (rounds, mode, split)."""

    def __init__(
        self,
        *,
        rounds: int,
        mode: str,
        split: int,
        batch_size: int,
        device: torch.device | str = "cpu",
        seed: int = 0,
        negative_fraction: float = 0.5,
        delta: int | None = None,
    ) -> None:
        if mode not in {"kpa", "cpa"}:
            raise ValueError(f"mode must be 'kpa' or 'cpa', got {mode!r}")
        if mode == "cpa" and delta is None:
            raise ValueError("cpa mode requires a nonzero delta")
        if not 0.0 <= negative_fraction <= 1.0:
            raise ValueError("negative_fraction must be in [0, 1]")
        self.rounds = rounds
        self.mode = mode
        self.split = split
        self.batch_size = batch_size
        self.device = torch.device(device)
        self.negative_fraction = negative_fraction
        self.delta = delta
        self.generator = torch.Generator(device=self.device)
        self.generator.manual_seed(seed)

    def _rand(self, n: int) -> torch.Tensor:
        return rand64(n, device=self.device, generator=self.generator)

    def _sample_keys(self, n: int) -> torch.Tensor:
        chunks: list[torch.Tensor] = []
        collected = 0
        while collected < n:
            candidate = self._rand(max(n, 64))
            selected = candidate[split_of(candidate) == self.split]
            if selected.numel():
                chunks.append(selected)
                collected += selected.numel()
        return torch.cat(chunks)[:n]

    def batch(self, batch_size: int | None = None) -> PairBatch:
        n = batch_size or self.batch_size
        keys = self._sample_keys(n)
        plaintext1 = self._rand(n)
        if self.mode == "cpa":
            plaintext2 = plaintext1 ^ int(self.delta)
        else:
            plaintext2 = self._rand(n)

        ciphertext1 = des_encrypt_torch(plaintext1, keys, self.rounds)
        ciphertext2 = des_encrypt_torch(plaintext2, keys, self.rounds)

        if self.negative_fraction > 0.0:
            negative = torch.rand(
                n, device=self.device, generator=self.generator
            ) < self.negative_fraction
            random1 = self._rand(n)
            random2 = self._rand(n)
            ciphertext1 = torch.where(negative, random1, ciphertext1)
            ciphertext2 = torch.where(negative, random2, ciphertext2)
            labels = (~negative).long()
        else:
            labels = torch.ones(n, dtype=torch.long, device=self.device)

        return PairBatch(plaintext1, plaintext2, ciphertext1, ciphertext2, keys, labels)
