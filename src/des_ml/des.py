"""Reference DES implementation with round-reduced variants.

This module is deliberately dependency-free and bit-exact.  It is the
ground truth against which the vectorised PyTorch implementation, the
experiment data generators and the CI conformance run are checked.

Conventions
-----------
* A block or key is an ``int`` whose bit 63 is the leftmost bit of the
  DES specification and whose bit 0 is the rightmost bit.
* ``rounds`` is the number of Feistel rounds actually executed.  A
  round-reduced cipher uses the first ``rounds`` round keys of the
  standard key schedule and still performs the final L/R swap, which is
  the usual definition of "r-round DES".
* Key parity bits are ignored by PC-1, so any 64-bit value is a valid
  key; the effective key is 56 bits.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = [
    "DES_ROUNDS",
    "key_schedule",
    "des_encrypt",
    "des_decrypt",
    "des_encrypt_states",
    "feistel",
    "permute",
    "sbox_output",
    "SBOXES",
]

DES_ROUNDS = 16

IP: tuple[int, ...] = (
    58, 50, 42, 34, 26, 18, 10, 2,
    60, 52, 44, 36, 28, 20, 12, 4,
    62, 54, 46, 38, 30, 22, 14, 6,
    64, 56, 48, 40, 32, 24, 16, 8,
    57, 49, 41, 33, 25, 17, 9, 1,
    59, 51, 43, 35, 27, 19, 11, 3,
    61, 53, 45, 37, 29, 21, 13, 5,
    63, 55, 47, 39, 31, 23, 15, 7,
)

IP_INV: tuple[int, ...] = (
    40, 8, 48, 16, 56, 24, 64, 32,
    39, 7, 47, 15, 55, 23, 63, 31,
    38, 6, 46, 14, 54, 22, 62, 30,
    37, 5, 45, 13, 53, 21, 61, 29,
    36, 4, 44, 12, 52, 20, 60, 28,
    35, 3, 43, 11, 51, 19, 59, 27,
    34, 2, 42, 10, 50, 18, 58, 26,
    33, 1, 41, 9, 49, 17, 57, 25,
)

E: tuple[int, ...] = (
    32, 1, 2, 3, 4, 5,
    4, 5, 6, 7, 8, 9,
    8, 9, 10, 11, 12, 13,
    12, 13, 14, 15, 16, 17,
    16, 17, 18, 19, 20, 21,
    20, 21, 22, 23, 24, 25,
    24, 25, 26, 27, 28, 29,
    28, 29, 30, 31, 32, 1,
)

P: tuple[int, ...] = (
    16, 7, 20, 21, 29, 12, 28, 17,
    1, 15, 23, 26, 5, 18, 31, 10,
    2, 8, 24, 14, 32, 27, 3, 9,
    19, 13, 30, 6, 22, 11, 4, 25,
)

PC1: tuple[int, ...] = (
    57, 49, 41, 33, 25, 17, 9,
    1, 58, 50, 42, 34, 26, 18,
    10, 2, 59, 51, 43, 35, 27,
    19, 11, 3, 60, 52, 44, 36,
    63, 55, 47, 39, 31, 23, 15,
    7, 62, 54, 46, 38, 30, 22,
    14, 6, 61, 53, 45, 37, 29,
    21, 13, 5, 28, 20, 12, 4,
)

PC2: tuple[int, ...] = (
    14, 17, 11, 24, 1, 5,
    3, 28, 15, 6, 21, 10,
    23, 19, 12, 4, 26, 8,
    16, 7, 27, 20, 13, 2,
    41, 52, 31, 37, 47, 55,
    30, 40, 51, 45, 33, 48,
    44, 49, 39, 56, 34, 53,
    46, 42, 50, 36, 29, 32,
)

SHIFTS: tuple[int, ...] = (1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1)

SBOXES: tuple[tuple[int, ...], ...] = (
    (
        14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7,
        0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8,
        4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0,
        15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13,
    ),
    (
        15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10,
        3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5,
        0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15,
        13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9,
    ),
    (
        10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8,
        13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1,
        13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7,
        1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12,
    ),
    (
        7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15,
        13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9,
        10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4,
        3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14,
    ),
    (
        2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9,
        14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6,
        4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14,
        11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3,
    ),
    (
        12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11,
        10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8,
        9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6,
        4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13,
    ),
    (
        4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1,
        13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6,
        1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2,
        6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12,
    ),
    (
        13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7,
        1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2,
        7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8,
        2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11,
    ),
)


def permute(value: int, table: Sequence[int], n_in: int) -> int:
    """Apply a DES bit permutation.

    ``table`` entries are 1-based positions counted from the most
    significant bit of an ``n_in``-bit input.
    """
    out = 0
    for position in table:
        out = (out << 1) | ((value >> (n_in - position)) & 1)
    return out


def _rotl28(value: int, amount: int) -> int:
    mask = (1 << 28) - 1
    amount %= 28
    return ((value << amount) | (value >> (28 - amount))) & mask if amount else value & mask


def key_schedule(key: int, rounds: int = DES_ROUNDS) -> list[int]:
    """Return ``rounds`` 48-bit round keys derived from a 64-bit key."""
    if not 1 <= rounds <= 16:
        raise ValueError(f"rounds must be in [1, 16], got {rounds}")
    if not 0 <= key < (1 << 64):
        raise ValueError("key must be a 64-bit integer")

    permuted = permute(key, PC1, 64)
    c = (permuted >> 28) & ((1 << 28) - 1)
    d = permuted & ((1 << 28) - 1)

    subkeys: list[int] = []
    for round_index in range(rounds):
        shift = SHIFTS[round_index]
        c = _rotl28(c, shift)
        d = _rotl28(d, shift)
        subkeys.append(permute((c << 28) | d, PC2, 56))
    return subkeys


def sbox_output(sbox_index: int, six_bits: int) -> int:
    """Apply S-box ``sbox_index`` to a 6-bit input (row/column addressing).

    ``SBOXES`` stores each box as 64 row-major entries indexed by
    ``row * 16 + column``; the 6-bit input is **not** that index.  Every
    S-box consumer must go through this function.
    """
    if not 0 <= sbox_index < 8:
        raise ValueError("sbox_index must be in [0, 7]")
    if not 0 <= six_bits < 64:
        raise ValueError("six_bits must be a 6-bit integer")
    row = ((six_bits & 0x20) >> 4) | (six_bits & 0x01)
    column = (six_bits >> 1) & 0x0F
    return SBOXES[sbox_index][row * 16 + column]


def feistel(right: int, subkey: int) -> int:
    """The DES round function f(R, K)."""
    expanded = permute(right, E, 32) ^ subkey
    substituted = 0
    for box_index in range(8):
        six_bits = (expanded >> (42 - 6 * box_index)) & 0x3F
        substituted = (substituted << 4) | sbox_output(box_index, six_bits)
    return permute(substituted, P, 32)


def _crypt(block: int, subkeys: Sequence[int]) -> int:
    if not 0 <= block < (1 << 64):
        raise ValueError("block must be a 64-bit integer")
    state = permute(block, IP, 64)
    left = (state >> 32) & 0xFFFFFFFF
    right = state & 0xFFFFFFFF
    for subkey in subkeys:
        left, right = right, left ^ feistel(right, subkey)
    # DES swaps the halves after the last round before the final permutation.
    return permute((right << 32) | left, IP_INV, 64)


def des_encrypt(block: int, key: int, rounds: int = DES_ROUNDS) -> int:
    """Encrypt one 64-bit block with ``rounds`` Feistel rounds."""
    return _crypt(block, key_schedule(key, rounds))


def des_decrypt(block: int, key: int, rounds: int = DES_ROUNDS) -> int:
    """Decrypt one 64-bit block encrypted with ``rounds`` rounds."""
    return _crypt(block, list(reversed(key_schedule(key, rounds))))


def des_encrypt_states(block: int, key: int, rounds: int = DES_ROUNDS) -> list[tuple[int, int]]:
    """Return ``[(L0, R0), ..., (L_r, R_r)]`` for intermediate states.

    The input state is ``IP(block) = L0 || R0``; each later pair is the
    state after that many Feistel rounds.  This is the oracle used by the
    differential-trail Monte Carlo validation.
    """
    if not 0 <= block < (1 << 64):
        raise ValueError("block must be a 64-bit integer")
    state = permute(block, IP, 64)
    left = (state >> 32) & 0xFFFFFFFF
    right = state & 0xFFFFFFFF
    states = [(left, right)]
    for subkey in key_schedule(key, rounds):
        left, right = right, left ^ feistel(right, subkey)
        states.append((left, right))
    return states
