# 0010. S-box chunk scorer and six-round differential attack

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Zephyr236, Claude Code

## Context

TH-1 produced validated trails but showed that a single 5-round
characteristic has probability around `2^-25`, so a naive DDT rank at 6
rounds needs hundreds of millions of pairs.  The project goal is a
working 6-round known/chosen-plaintext attack with an AI component; the
2- and 4-round stages are the testbed.

## Decision

1. **Last-round chunk scorer.** For a ciphertext pair and S-box `j`, a
   candidate 6-bit chunk key determines four corrected bits of
   `L_{R-1}`.  The scorer is initialised with the exact log-DDT logit
   (zero residual head) and learns a correction from the full pair
   context (plaintexts, last-round words).  Training uses listwise CE
   over the 64 candidates; each S-box has its own output head on a
   shared trunk.
2. **Two-round evidence.** The scorer is trained at 2 rounds first.
   The DDT counter is at chance there; the neural residual reaches
   chunk accuracy 0.39 and top-5 0.77, which establishes that the
   learning pipeline works.  Boxes 3 and 5 remain weak; a full 2-round
   key recovery with the current checkpoint is not claimed.
3. **Six-round differential attack.** Use the full-active 5-round trail
   (`DeltaP=0x0000001010000000`, `p=2^-25.268`, last-round input
   differences `[8,1,19,48,8,4,2,32]`).  Filter pairs by that
   key-independent vector, then test each candidate chunk key by the
   **characteristic match**: partially decrypt the last round and check
   the trail's predicted `L5` difference.  Take top-k per S-box, invert
   the key schedule (256 completions per 48-bit round key), and verify
   every master key by real re-encryption.  The plain log-DDT rank is
   kept as a negative baseline: over a handful of filtered pairs it
   scores wrong high-probability output differences above true right
   pairs, and a partial filter with ~5k non-right pairs is diluted.
4. **AI scaling is reported honestly.** Six-round chunk-scorer and
   PairCNN distinguisher training were started and did not move above
   chance in the early evaluations.  The six-round key recovery
   therefore uses the DDT backbone; the neural scorer is the AI
   component at 2 rounds.  A neural improvement at 6 rounds is a
   follow-up, not an assumed result.
5. **Complexity.** The six-round run uses 323M chosen plaintext pairs
   for one target key, reports the filtered-pair count and the true
   chunk ranks, and counts only re-encryption as success.

## Consequences

- The six-round attack is a single-key demonstration with large data
  complexity, not a practical break of DES.
- The right-pair filter is key-independent and can be applied before
  any key guess; it removes most noise and makes the DDT rank usable.
- **Result:** the match test over 323M pairs kept four pairs and put
  all true chunks at rank 1.5; top-2 recovered the effective key
  `0x123456789ABCDEF0`, parity-equivalent to the target
  `0x133457799BBCDFF1`, and passed real re-encryption.
- The chunk scorer's weak S-boxes at 2 rounds and the flat 6-round
  neural training are recorded as negative results.
- A future neural scorer must beat the DDT rank on held-out keys; the
  current run sets that baseline.

## Alternatives considered

- **Five-round characteristic only.** At `2^-25`, unfiltered DDT rank
  over 100M pairs is near chance (mean rank 29.2 of 64, partial box
  signal).  The full-filter run over 323M pairs kept only four pairs;
  the plain DDT rank stayed at chance, which motivated the
  characteristic-match test.
- **End-to-end 56-bit key regression.** No sample-efficient path.
- **A neural distinguisher as the 6-round claim.** Early training did
  not learn; a distinguishing claim would be weaker than the key
  recovery attempted here.
