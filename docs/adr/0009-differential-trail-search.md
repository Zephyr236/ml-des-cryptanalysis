# 0009. Differential trail search and validation

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Zephyr236, Claude Code

## Context

The DDT rank baseline showed that an arbitrary plaintext difference carries
no usable last-round signal. Classical differential attacks select a
high-probability characteristic and keep right pairs. We need concrete
trails for round-reduced DES, plus a validation that the search output is
a real property of the cipher rather than a bookkeeping error.

Exhaustive enumeration of all differential trails is infeasible beyond
one or two rounds: each active S-box branches into up to 16 output
differences, and there are eight S-boxes per round.

## Decision

1. **Beam search over Feistel difference states.** A state is
   `(ΔL, ΔR)`; a round is `(ΔL, ΔR) -> (ΔR, ΔL xor P(b))`, where `b` is a
   choice of output difference for every active S-box. The probability of
   the round is the product of `DDT[a_j][b_j] / 64`; inactive boxes
   contribute 1.
2. **Start set.** All 64 single-bit differences in `ΔL` or `ΔR`. The set
   is part of the run config; a different set is a different experiment.
3. **Branching and pruning.** For each state, keep the top `branch`
   output differences per active S-box and the top `combos` combinations
   by log-probability. Merge equal next states, keep the better path, and
   retain the best `beam` states per round.
4. **Two outputs per round count.** `best` may be a trivial trail with no
   active S-box (one round of deterministic Feistel propagation);
   `best_active` requires at least one active S-box and is the trail used
   for key-recovery work. Both are reported.
5. **Lower-bound semantics.** A found trail is a valid characteristic.
   The search does **not** prove optimality; beam, branch, combos and the
   start set must be reported with every trail.
6. **Validation.** Sample plaintext pairs with the trail's input
   difference under random keys, run the real cipher, and count pairs
   whose full state-difference path matches the trail at every round.
   The empirical frequency must be at least `p - 3*sqrt(p(1-p)/N)`; a
   lower frequency rejects the trail. Validation rounds and sample counts
   are recorded in the manifest.
7. **Use.** Only validated active trails are used to choose CPA deltas
   and right-pair filters. A trail's last-round S-box input differences
   are the filter target for the chunk-ranking attack.
8. **Power before proposals.** Every trail reports `N*p` at the current
   pair budget and the pairs needed for 1, 10 and 100 right pairs. A
   trail is only proposed for a downstream attack when that requirement
   is feasible at the planned key count; an unvalidated or underpowered
   trail is recorded, not promoted.
9. **Two-sided interval, one-sided rejection.** Validation reports a
   Wilson interval for the empirical frequency. The pass rule is
   one-sided (`empirical >= p - 3*sigma`) because other trails can
   collide into the same state path and only increase the observed rate;
   the interval is still reported so an unexpectedly high rate is
   visible.
10. **Beam sensitivity.** The run records the best active log2
    probability for several beam widths. A lower bound that moves with
    the beam width is reported as such; it is not a certificate.
11. **Indexing.** S-box inputs/outputs are reported as 0-based array
    indices (`S1=0, ..., S8=7`). Every trail artefact states this.

## Consequences

- The search may miss a better trail. A result is "the best found under
  these parameters", never "the best characteristic".
- The characteristic probability is not the differential probability;
  other trails can contribute to the same output difference. Validation
  checks the trail event, not the full differential.
- The 1-round trivial trail is probability 1 and is not used to claim a
  distinguisher; it is reported for completeness and separated from
  `best_active`.
- An unvalidated trail cannot be used in a downstream attack.
- A trail whose required pair budget is infeasible is reported as a
  boundary/negative result, not as a candidate.
- Beam sensitivity is evidence about the search, not a proof of
  optimality; the classical ceiling remains a separate experiment.

## Alternatives considered

- **Exhaustive enumeration.** Correct but exponential; only usable for
  one round / one S-box.
- **Matsui branch-and-bound.** Better optimality guarantees, but needs a
  reliable bound on the remaining active S-boxes; beam search is simpler
  and sufficient for a first characteristic.
- **Random search / genetic algorithms.** Less reproducible and harder to
  state as a lower bound; rejected for the first TH-1 run.
