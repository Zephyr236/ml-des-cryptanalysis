# 0005. DES conventions and round-reduced semantics

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Zephyr236, Claude Code

## Context

The project has two DES implementations (a pure-Python reference and a
vectorised PyTorch evaluator), an attack that partially decrypts the
last round, and a key-schedule decoder. A single bit-order or
final-swap mistake would silently invalidate every metric. The roadmap
requires the last-round algebra to be stated once, consistently, and
tested against an external standard.

## Decision

1. **Bit numbering.** A block or key is a 64-bit pattern held in a
   signed `int64` / Python `int`. Integer bit 63 is DES specification
   bit 1 (the leftmost bit); integer bit 0 is specification bit 64.
2. **Tables.** IP, IP⁻¹, E, P, PC-1, PC-2, the eight S-boxes and the
   rotation schedule are taken from FIPS PUB 46-3 and live only in
   `src/des_ml/des.py`. The PyTorch evaluator imports those tables; it
   does not duplicate them.
3. **Round count.** `r`-round DES executes the first `r` subkeys of the
   standard key schedule, performs the final L/R swap, and applies
   IP⁻¹. Decryption reverses the subkey order. This is the definition
   used by every config, test and manifest.
4. **Key equivalence.** PC-1 discards the eight parity bits
   (specification bits 8, 16, …, 64). The **56-bit effective key** is
   `PC1(key)`; keys that differ only in parity are the same key and must
   map to the same data split.
5. **Last-round algebra.** Let `C` be an `r`-round ciphertext and
   `IP(C) = R_r ‖ L_r`. Then
   `R_{r-1} = L_r` and `L_{r-1} = R_r ⊕ f(L_r, K_r)`, where `f` is the
   round function. For a plaintext pair, the expansion input difference
   `E(L_r)_j ⊕ E(L'_r)_j` is key-independent because the round key
   cancels. This is the equation the chunk scorer relies on.
6. **Key-schedule coverage.** Each 48-bit round key selects 48 distinct
   master bits; eight master bits are absent, so a hard decode has
   exactly `2^8 = 256` completions. Coverage of any set of observed
   round keys is **computed from PC-1/PC-2/rotations at runtime and
   asserted**, never assumed from a hand-written claim.
7. **Verification.** A revision is conformant only if:
   - the FIPS KAT passes
     (`K=0x133457799BBCDFF1`, `P=0x0123456789ABCDEF`,
     `C=0x85E813540F0AB405`);
   - the complementation identity holds (`E(¬P, ¬K) = ¬E(P, K)`);
   - every round count in 1..16 round-trips;
   - the PyTorch evaluator agrees bit-for-bit with the reference on
     `10^6` random vectors, and the conformance run records the result.
8. **Signed storage.** PyTorch stores 64-bit patterns in `int64`; values
   with the top bit set are negative. Bit extraction masks after every
   shift. Comparisons to the Python reference mask with `2^64 − 1`.

## Consequences

- Any change to a table, the final swap, or the round-count definition
  is a watched-path change requiring a new ADR and a new conformance
  run.
- The signed-storage convention is documented in `des_torch.py`; tests
  cover the sign boundary explicitly.
- The attack code may use either the swapped or unswapped convention
  internally, but each module must state which one and test against the
  public `des_decrypt` at its boundary.

## Alternatives considered

- **Unsigned `uint64` storage.** PyTorch support is incomplete for
  shifts and indexing; signed patterns with masking are equivalent.
- **A single implementation.** The reference is too slow for data
  generation and the vectorised version is too complex to trust without
  an independent oracle; two implementations are the point.
