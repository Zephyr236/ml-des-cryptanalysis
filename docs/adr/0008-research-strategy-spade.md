# 0008. Research strategy: SPADE, not end-to-end key regression

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Zephyr236, Claude Code
- **Inputs:** four independent design proposals and three reviews
  (cryptographic rigor, ML methodology, compute feasibility); all three
  reviews ranked the structure-informed arm first.

## Context

The previous stage trained a network to map `(P, C*)` and a candidate
key to a better candidate, and reached ~27% at 2 rounds. At 16 bits the
key space is small enough that brute force dominates; at 56 bits a
regression over the key has no chance, and a learned smooth surrogate of
DES is neither necessary nor sample-efficient.

DES is not a generic black box. Its last round exposes an exact
likelihood-ratio decomposition and its key schedule is GF(2)-linear.
A strategy that ignores this structure spends capacity relearning public
algebra and makes leakage harder to rule out.

## Decision

1. **Base arm: SPADE** (Structure-Prior Attack on DES):
   S-box-factorised last-round chunk scoring, a DDT-initialised
   residual, sum-pooled log-likelihood aggregation, exact key-schedule
   decoding, and exact re-encryption verification.
   - Eight independent 64-way hypotheses, one per S-box.
   - `g = 0` reproduces the classical log-DDT attack exactly, so the
     neural contribution is measurable as a residual, not as a
     from-scratch classifier.
   - Sum pooling of per-pair log-odds is the Bayes-optimal aggregation
     for iid pairs and preserves data-complexity scaling.
   - Hard decoding enumerates the exact 2^8 master-key completions.
2. **Rejected as primary arms:**
   - **End-to-end 56-bit regression / candidate refinement.** The
     search-distribution shift makes the residual statistically uniform
     at the distances where beam search must start; the compute and
     leakage surface are highest.
   - **A pure distinguisher + single-S-box ranking.** Correct, but it
     changes only four ciphertext bits per candidate and is structurally
     starved of candidate-dependent leverage; it remains a baseline.
   - **A pure measurement/probing study.** Excellent statistics, but it
     is not an attack; its methods are grafted into the control suite.
3. **Mandatory grafts:** pre-registered falsifiers F1–F6 (ADR-0006);
   temperature scaling and ECE gate; paired bootstrap on identical
   keys/pairs; Holm correction; exact classical ceiling (DDT/LAT,
   trails, multi-trail, Matsui linear) before any neural claim;
   representation/decoder probes; DES-24/32 exhaustive rank validation;
   shuffled-S-box, random-Feistel, wrong-α, permuted-P and R = 16
   negative controls; listwise 64-way training objective; zero-oracle
   confirmatory mode.
4. **The current PairCNN is a baseline, not the plan.** It remains in
   the repository as the "unstructured pair MLP/CNN" comparator and as
   the smoke-test model. Stage 1 experiments use SPADE.
5. **Implementation modules:** exact DES and feature extractor,
   chunk scorer, optional pair-context encoder, sum pooling, schedule
   decoder, verifier, and a Gumbel-softmax relaxed core used only as an
   ablation.

## Consequences

- Stage 1 is blocked on the SPADE implementation (issue #4); the
  existing distinguisher configs are relabelled as baselines in the
  experiment register.
- The feature interface is physically unable to see `K*`; a leak canary
  is a hard gate.
- The neural margin may be zero. That is a pre-registered acceptable
  outcome (F2), and the pipeline is designed to measure it rather than
  hide it.
- Compute stays under ~2.5 GB VRAM for the scorer; the 6 GB card has
  headroom for data generation and evaluation sweeps.

## Alternatives considered

- **Full 56-bit classifier.** Key space too large; no sample-efficient
  path.
- **End-to-end differentiable DES with straight-through S-boxes.**
  Gradients through 16 rounds are vanishing and the relaxation is not
  the cipher; kept only as ablation AB-5.
- **Pure classical attack reproduction.** Useful as a ceiling, but it
  would not answer the research question about learned residuals.

### Stage 1 ordering update (2026-11-26)

A first exact log-DDT rank baseline with 64 unfiltered pairs and a
one-bit delta is at chance for R=4/6/8 (mean rank ~32.5, top-1 ~1/64;
runs recorded in `docs/EXPERIMENTS.md`). This does not test SPADE: the
planned DG-4 uses the best available characteristic and right-pair
filtering. It does establish two ordering constraints: TH-1 trail
selection must precede DG-4, and every "no signal" result must state the
delta, the filtering rule and the pair budget. An arbitrary delta is not
a valid stand-in for a characteristic.
