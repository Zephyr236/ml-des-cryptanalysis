# 0006. Pre-registered endpoints and falsifiers

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Zephyr236, Claude Code
- **Freeze rule:** the endpoints below are frozen before any confirmatory
  run. Changing them after seeing results requires a new ADR, a new
  issue, and the changed analysis is labelled exploratory.

## Context

The most likely honest outcome is that a neural scorer adds nothing
measurable on top of the exact differential distribution at feasible
budgets. If the endpoint is chosen after seeing the numbers, that
outcome can be quietly reframed as a success. This ADR fixes the
questions and the decision rules in advance.

## Decision

### Primary endpoint (F1)

At **R = 8, CPA**, with budget matched on total work (oracle queries +
key trials × pairs + verifier encryptions), compare the SPADE pipeline
against a budget-matched classical differential attack. The claim
"ML extends differential key recovery at R = 8" is **dead** if the
one-sided 95% lower confidence bound on
`success@1(ML) − success@1(classical)` is ≤ 0.

`success@1` means the exact 56-bit master key is recovered by the first
verified candidate, where verification is real re-encryption on held-out
pairs.

### Secondary falsifiers

- **F2 (learning beyond the DDT).** The DDT-initialised residual's chunk
  AUC must exceed the exact log-DDT counter by a pre-registered margin
  (ΔAUC ≥ 0.02, or ≥ 2× fewer pairs to 50% chunk top-1) at some
  `R ∈ {6, 8, 10}`. Otherwise the conclusion is "learning adds nothing
  beyond the differential distribution". The F2 family is
  Holm–Bonferroni corrected over 7 rounds × 8 S-boxes = 56 cells.
- **F3 (structure).** If the shuffled-S-box control matches the DES
  S-box result, the effect is not DES-structural and the claim is
  invalid.
- **F4 (evaluation integrity).** If the leak-canary probe separates
  `K*` above chance, or the R = 16 negative control succeeds, all
  claims are halted pending a bug investigation.
- **F5 (calibration).** If expected calibration error after temperature
  scaling exceeds 0.10 on held-out keys, no posterior/LLR-aggregation
  claim is made.
- **F6 (replay).** If a headline cell does not reproduce within the
  stated tolerance from a clean checkout driven only by its manifest,
  the claim is withdrawn or restated as non-reproducible.

### Statistics fixed in advance

- Seeds 0–4 for `R ≤ 8`, seeds 0–2 for `R ≥ 10`.
- Primary endpoint: one-sided α = 0.05, no correction.
- F2 family: Holm–Bonferroni over 56 cells.
- Rank and success intervals: bootstrap over test keys (10,000
  resamples); paired bootstrap against baselines on identical
  `(key, pair)` sets.
- Every null reports a power analysis / minimum detectable effect.
- Every run is reported, including failures and wall-clock-censored
  runs. Censoring is a result, not a deletion.

### Gates that must pass before a claim is drafted

1. DES conformance (ADR-0005).
2. VA-1 exhaustive rank validation on DES-24/DES-32.
3. Leak canary at chance.
4. R = 16 negative control at chance.
5. Control suite (shuffled S-box, random Feistel, label shuffle,
   wrong-α, permuted P) behaving as null.

## Consequences

- A negative F1 is a publishable result and does not block Stage 5.
- A surprising positive at `R ≥ 10` is treated as a bug or leakage until
  the controls explain it.
- The report must separate **confirmed**, **bounds**, and
  **speculation**; a claim that cannot name its endpoint is not a claim.

## Alternatives considered

- **Choose the endpoint after a pilot.** Rejected: pilots leak
  information and turn confirmatory tests into exploratory ones. A pilot
  may inform power calculations but not the endpoint definition.
- **A single composite score.** Rejected: it hides which falsifier
  fired and invites post-hoc weighting.
