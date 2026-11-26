"""Bit-exact, batched DES in PyTorch.

The implementation mirrors :mod:`des_ml.des` operation for operation but
works on ``torch.int64`` tensors so that millions of encryptions can be
produced on the GPU.  It is *not* differentiable with respect to the key
or the plaintext: the S-box and the bit permutations are discrete.  It is
the exact evaluator used for data generation, candidate-key scoring and
attack verification.  A soft/differentiable variant lives in
``des_ml.soft_des`` and is used only for probing experiments.

All tensors are ``torch.int64``.  Keys may be a scalar, a ``(B,)`` tensor
or broadcastable to the block batch.  ``rounds`` selects a round-reduced
variant using the first ``rounds`` subkeys.
"""

from __future__ import annotations

import torch

from .des import (
    IP,
    IP_INV,
    PC1,
    PC2,
    SBOXES,
    SHIFTS,
    E,
    P,
)

__all__ = [
    "des_encrypt_torch",
    "des_decrypt_torch",
    "des_encrypt_states_torch",
    "key_schedule_torch",
    "feistel_torch",
    "permute_torch",
    "effective_key_torch",
    "rand64",
]

_MASK28 = (1 << 28) - 1
_SBOX_FLAT = torch.tensor([box for box in SBOXES], dtype=torch.long)  # (8, 64)


def _as_tensor(value, like: torch.Tensor) -> torch.Tensor:
    if isinstance(value, torch.Tensor):
        return value.to(device=like.device, dtype=torch.long)
    return torch.tensor(value, dtype=torch.long, device=like.device)


def permute_torch(value: torch.Tensor, table: tuple[int, ...], n_in: int) -> torch.Tensor:
    """Apply a DES bit permutation to every element of ``value``."""
    out = torch.zeros_like(value)
    n_out = len(table)
    for index, position in enumerate(table):
        bit = (value >> (n_in - position)) & 1
        out = out | (bit << (n_out - 1 - index))
    return out


def _rotl28(value: torch.Tensor, amount: int) -> torch.Tensor:
    amount %= 28
    if amount == 0:
        return value & _MASK28
    return ((value << amount) | (value >> (28 - amount))) & _MASK28


def key_schedule_torch(key: torch.Tensor, rounds: int = 16) -> list[torch.Tensor]:
    if not 1 <= rounds <= 16:
        raise ValueError(f"rounds must be in [1, 16], got {rounds}")
    permuted = permute_torch(key, PC1, 64)
    c = (permuted >> 28) & _MASK28
    d = permuted & _MASK28
    subkeys: list[torch.Tensor] = []
    for round_index in range(rounds):
        shift = SHIFTS[round_index]
        c = _rotl28(c, shift)
        d = _rotl28(d, shift)
        subkeys.append(permute_torch((c << 28) | d, PC2, 56))
    return subkeys


def effective_key_torch(key: torch.Tensor) -> torch.Tensor:
    """Return the 56-bit effective key (parity bits removed by PC-1)."""
    return permute_torch(key, PC1, 64)


def feistel_torch(right: torch.Tensor, subkey: torch.Tensor) -> torch.Tensor:
    expanded = permute_torch(right, E, 32) ^ subkey
    substituted = torch.zeros_like(right)
    sbox = _SBOX_FLAT.to(device=right.device)
    for box_index in range(8):
        six = (expanded >> (42 - 6 * box_index)) & 0x3F
        row = ((six & 0x20) >> 4) | (six & 0x01)
        column = (six >> 1) & 0x0F
        values = sbox[box_index][row * 16 + column]
        substituted = (substituted << 4) | values
    return permute_torch(substituted, P, 32)


def _crypt(block: torch.Tensor, subkeys: list[torch.Tensor]) -> torch.Tensor:
    state = permute_torch(block, IP, 64)
    left = (state >> 32) & 0xFFFFFFFF
    right = state & 0xFFFFFFFF
    for subkey in subkeys:
        new_right = left ^ feistel_torch(right, subkey)
        left, right = right, new_right
    return permute_torch((right << 32) | left, IP_INV, 64)


def des_encrypt_torch(block: torch.Tensor, key, rounds: int = 16) -> torch.Tensor:
    block = block.to(dtype=torch.long)
    key = _as_tensor(key, block)
    return _crypt(block, key_schedule_torch(key, rounds))


def des_decrypt_torch(block: torch.Tensor, key, rounds: int = 16) -> torch.Tensor:
    block = block.to(dtype=torch.long)
    key = _as_tensor(key, block)
    return _crypt(block, list(reversed(key_schedule_torch(key, rounds))))


def des_encrypt_states_torch(
    block: torch.Tensor, key, rounds: int = 16
) -> list[tuple[torch.Tensor, torch.Tensor]]:
    """Batched ``[(L0,R0), ..., (L_r,R_r)]`` for the Monte Carlo check."""
    block = block.to(dtype=torch.long)
    key = _as_tensor(key, block)
    state = permute_torch(block, IP, 64)
    left = (state >> 32) & 0xFFFFFFFF
    right = state & 0xFFFFFFFF
    states = [(left, right)]
    for subkey in key_schedule_torch(key, rounds):
        left, right = right, left ^ feistel_torch(right, subkey)
        states.append((left, right))
    return states


def rand64(
    n: int,
    *,
    device: torch.device | str = "cpu",
    generator: torch.Generator | None = None,
) -> torch.Tensor:
    """Uniform 64-bit integers, built from two 32-bit draws.

    ``torch.randint`` cannot express the full unsigned 64-bit range, so
    two 32-bit halves are combined instead.
    """
    high = torch.randint(0, 1 << 32, (n,), dtype=torch.long, device=device, generator=generator)
    low = torch.randint(0, 1 << 32, (n,), dtype=torch.long, device=device, generator=generator)
    return (high << 32) | low
