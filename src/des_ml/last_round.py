"""Last-round partial decryption and chunk features.

For an ``r``-round ciphertext ``C``, ``IP(C) = R_r || L_r``.  The previous
state is ``R_{r-1} = L_r`` and

    L_{r-1} = R_r xor f(L_r, K_r).

The round function's S-boxes are independent, so a 6-bit candidate for
S-box ``j`` determines exactly four bits of ``L_{r-1}``: those at the
P-permutation images of that S-box's output nibble.  This module exposes
that algebra without touching the master key.
"""

from __future__ import annotations

import numpy as np

from .des import IP, E, P, des_encrypt, key_schedule, permute, sbox_output
from .theory.ddt import log_ddt

__all__ = [
    "last_round_words",
    "sbox_input",
    "chunk_positions",
    "apply_chunk",
    "chunk_bits",
    "previous_state",
    "true_round_key",
    "true_chunk_key",
    "chunk_ddt_score",
]


def last_round_words(ciphertext: int) -> tuple[int, int]:
    """Return ``(R_r, L_r)`` from an ``r``-round ciphertext."""
    state = permute(ciphertext, IP, 64)
    return (state >> 32) & 0xFFFFFFFF, state & 0xFFFFFFFF


def sbox_input(left: int, sbox_index: int) -> int:
    """The 6-bit input to S-box ``sbox_index`` (0-based) given ``L_r``."""
    expanded = permute(left, E, 32)
    return (expanded >> (42 - 6 * sbox_index)) & 0x3F


def chunk_positions(sbox_index: int) -> tuple[int, ...]:
    """Bit indices (0-based, MSB-first) in the round-function output
    ``f(L_r, K_r)`` that carry S-box ``j``'s four output bits.

    P maps pre-P bit ``P[i]`` (1-based) to output bit ``i``; the bits of
    S-box ``j`` live at pre-P positions ``4j+1 .. 4j+4``, so their output
    positions are the indices ``i`` with ``P[i]`` in that range.
    """
    if not 0 <= sbox_index < 8:
        raise ValueError("sbox_index must be in [0, 7]")
    source = set(range(4 * sbox_index + 1, 4 * sbox_index + 5))
    return tuple(i for i, source_position in enumerate(P) if source_position in source)


def apply_chunk(right_r: int, left_r: int, candidate: int, sbox_index: int) -> int:
    """Return ``L_{r-1}`` with only S-box ``j``'s contribution applied.

    Bits outside ``chunk_positions(j)`` are copied from ``R_r`` and are
    not meaningful; this value exists to extract the four corrected bits.
    """
    if not 0 <= candidate < 64:
        raise ValueError("candidate must be a 6-bit integer")
    six = sbox_input(left_r, sbox_index) ^ candidate
    substituted = sbox_output(sbox_index, six)
    pre_p = (substituted & 0xF) << (28 - 4 * sbox_index)
    return right_r ^ permute(pre_p, P, 32)


def chunk_bits(right_r: int, left_r: int, candidate: int, sbox_index: int) -> tuple[int, ...]:
    """The four corrected bits of ``L_{r-1}`` for one S-box candidate."""
    value = apply_chunk(right_r, left_r, candidate, sbox_index)
    return tuple((value >> (31 - position)) & 1 for position in chunk_positions(sbox_index))


def previous_state(plaintext: int, key: int, rounds: int) -> tuple[int, int]:
    """Return ``(R_{r-1}, L_{r-1})`` using the real cipher."""
    if rounds < 1:
        raise ValueError("rounds must be >= 1")
    if rounds == 1:
        # There is no "0-round ciphertext": the state before round 1 is
        # IP(P) = L_0 || R_0, without the final swap that every real
        # ciphertext receives.
        state = permute(plaintext, IP, 64)
        return state & 0xFFFFFFFF, (state >> 32) & 0xFFFFFFFF
    block = des_encrypt(plaintext, key, rounds - 1)
    state = permute(block, IP, 64)
    return (state >> 32) & 0xFFFFFFFF, state & 0xFFFFFFFF


def true_round_key(key: int, rounds: int) -> int:
    return key_schedule(key, rounds)[-1]


def true_chunk_key(key: int, rounds: int, sbox_index: int) -> int:
    return (true_round_key(key, rounds) >> (42 - 6 * sbox_index)) & 0x3F


def chunk_ddt_score(
    ciphertext1: int,
    ciphertext2: int,
    candidate: int,
    sbox_index: int,
    ddt: np.ndarray,
) -> float:
    """Exact log-DDT score for one S-box candidate on one ciphertext pair.

    ``ddt`` is the ``(64, 16)`` table for this S-box.
    """
    _, left1 = last_round_words(ciphertext1)
    _, left2 = last_round_words(ciphertext2)
    input1 = sbox_input(left1, sbox_index)
    input2 = sbox_input(left2, sbox_index)
    difference = input1 ^ input2
    output1 = sbox_output(sbox_index, input1 ^ candidate)
    output2 = sbox_output(sbox_index, input2 ^ candidate)
    return log_ddt(ddt, difference, output1 ^ output2)
