"""Key-schedule coverage and inversion.

The DES key schedule is a bit-selection map followed by rotations: PC-1
selects 56 of the 64 key bits, the two 28-bit halves rotate, and PC-2
selects 48 of the 56.  One round key therefore observes 48 **master**
bits and leaves 8 unobserved, giving exactly ``2^8 = 256`` master-key
completions.  This module computes that statement from the tables
rather than assuming it (ADR-0005).
"""

from __future__ import annotations

from .des import PC1, PC2, SHIFTS, key_schedule

__all__ = [
    "round_key_master_positions",
    "coverage",
    "recover_master_keys",
    "master_key_from_round_key",
    "PARITY_BITS",
]

PARITY_BITS = tuple(range(8, 65, 8))  # 1-based DES specification positions


def _get_bit(value: int, width: int, position: int) -> int:
    """Read a 1-based, MSB-first bit from ``value``."""
    return (value >> (width - position)) & 1


def _set_bit(value: int, width: int, position: int, bit: int) -> int:
    shift = width - position
    return (value & ~(1 << shift)) | ((bit & 1) << shift)


def _rotr28(value: int, amount: int) -> int:
    amount %= 28
    if amount == 0:
        return value & ((1 << 28) - 1)
    return ((value >> amount) | (value << (28 - amount))) & ((1 << 28) - 1)


def round_key_master_positions(round_index: int) -> list[int]:
    """Map each of the 48 bits of round key ``round_index`` (1-based) to a
    master-key bit position (1-based, MSB-first)."""
    if not 1 <= round_index <= 16:
        raise ValueError("round_index must be in [1, 16]")
    shift = sum(SHIFTS[:round_index]) % 28
    positions: list[int] = []
    for cd_position in PC2:
        half = 0 if cd_position <= 28 else 28
        local = cd_position - half  # 1..28 inside the half
        original_local = ((local - 1 - shift) % 28) + 1
        original_cd = half + original_local
        positions.append(PC1[original_cd - 1])
    return positions


def coverage(rounds: int | list[int] | tuple[int, ...]) -> set[int]:
    """Return the set of master-key bits observed by one or more round keys."""
    if isinstance(rounds, int):
        rounds = [rounds]
    observed: set[int] = set()
    for round_index in rounds:
        observed.update(round_key_master_positions(round_index))
    return observed


def recover_master_keys(round_key: int, round_index: int) -> list[int]:
    """Enumerate the 256 master keys consistent with a 48-bit round key.

    Parity bits are set to zero; DES ignores them.  Every returned key
    reproduces ``round_key`` at ``round_index``.
    """
    if not 0 <= round_key < (1 << 48):
        raise ValueError("round_key must be a 48-bit integer")
    if not 1 <= round_index <= 16:
        raise ValueError("round_index must be in [1, 16]")

    shift = sum(SHIFTS[:round_index]) % 28
    observed_positions = set(PC2)
    cd_rotated = 0
    for bit_index, cd_position in enumerate(PC2):
        cd_rotated = _set_bit(
            cd_rotated, 56, cd_position, _get_bit(round_key, 48, bit_index + 1)
        )
    unknown = [p for p in range(1, 57) if p not in observed_positions]
    if len(unknown) != 8:
        raise AssertionError(f"expected 8 unobserved bits, got {len(unknown)}")

    keys: list[int] = []
    for assignment in range(1 << len(unknown)):
        cd = cd_rotated
        for index, cd_position in enumerate(unknown):
            cd = _set_bit(cd, 56, cd_position, (assignment >> index) & 1)

        c_rotated = (cd >> 28) & ((1 << 28) - 1)
        d_rotated = cd & ((1 << 28) - 1)
        c0 = _rotr28(c_rotated, shift)
        d0 = _rotr28(d_rotated, shift)
        cd0 = (c0 << 28) | d0

        key = 0
        for bit_index, master_position in enumerate(PC1):
            key = _set_bit(key, 64, master_position, _get_bit(cd0, 56, bit_index + 1))
        keys.append(key)
    return keys


def master_key_from_round_key(round_key: int, round_index: int, *, verify_with: int | None = None) -> list[int]:
    """Recover candidates and optionally filter them by re-encryption.

    ``verify_with`` is a plaintext rotated by the true ciphertext, i.e.
    the caller passes ``(plaintext, ciphertext)`` indirectly; this helper
    exists for tests and is not used in the attack path.
    """
    candidates = recover_master_keys(round_key, round_index)
    if verify_with is None:
        return candidates
    plaintext, ciphertext = verify_with
    from .des import des_encrypt

    return [
        key
        for key in candidates
        if des_encrypt(plaintext, key, round_index) == ciphertext
    ]


def assert_round_key_reproduced(key: int, round_index: int) -> None:
    """Internal sanity helper used by tests and the theory report."""
    subkeys = key_schedule(key, 16)
    round_key = subkeys[round_index - 1]
    recovered = recover_master_keys(round_key, round_index)
    if not recovered:
        raise AssertionError("no candidates recovered")
