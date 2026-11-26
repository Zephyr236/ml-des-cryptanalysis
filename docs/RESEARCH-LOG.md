## 2026-11-26 — TH-1 differential trails found and validated

**What.** Beam search over 64 single-bit start differences produced active
trails for R=1..5. Run `20261126T135117Z-fc37e176-f9c5d98f-s0`.

**Validation.** The full state-difference path was sampled on the real
cipher: r=1 0.25028 vs 0.25 (n=100k), r=2 0.24907 vs 0.25 (n=500k),
r=3 0.007316 vs 0.007324 (n=1M). All three pass the ADR-0009 one-sided
check.

**Key trails.** The r=3 trail (`ΔP=0x1000`, p=2^-7.093) has last-round
S-box input differences `[0,8,0,0,0,0,0,8]`; it is the first real
candidate for a characteristic-filtered DDT rank on 4 rounds. The r=4
trail (`ΔP=0x10000`, p=2^-17.642) is the candidate for 5 rounds. The r=5
trail (`2^-27.694`) is too weak for a feasible R=6 attack at 64 pairs.

**Caveat.** The search is a lower bound under `beam=2000, branch=4,
combos=12`; a wider search may find better trails.

**Next.** Filter pairs by the r=3 last-round `a_j`, rerun the DDT rank on
4 rounds, and measure the true chunk rank for S1 and S7. Then repeat for
5 rounds with the r=4 trail.

## 2026-11-26 — DDT rank baseline is at chance without a characteristic

**What.** Six exact log-DDT runs: R=4/6/8, KPA and CPA (one-bit delta),
128 key-disjoint test keys x 64 pairs. Mean rank of the true last-round
chunk stays near 32.5 and top-1 near 1/64 in every cell.

**Interpretation.** Unfiltered pairs carry no usable last-round DDT
signal at this budget. Classical differential attacks do not use
unfiltered pairs: they choose a high-probability characteristic and keep
right pairs. The result therefore does not test SPADE's DDT-initialised
scorer; it says the initialisation must come from a real characteristic
and that pair filtering is a prerequisite. A "no signal" claim must
always name the delta, the filtering rule and the pair budget.

**Next.** TH-1 trail search, then re-run the rank baseline with the best
characteristic and right-pair filtering before training DG-4.

## 2026-11-26 — Merge provenance fix

**What.** Squash merge rewrites branch commits, so the manifests merged
in PR #12 and PR #14 pointed at commits that would stop being ancestors
of `main`. The repository now uses merge commits only, the
`main-provenance` workflow audits every push to `main`, and the heads of
the two affected PRs are preserved as `archive/pr-12-head` and
`archive/pr-14-head` tags.

**Why.** A result is only reproducible if the commit recorded in its
manifest can still be checked out from the repository. Provenance is
part of the experiment, not bookkeeping.

## 2026-11-26 — Theory core (DDT/LAT, schedule coverage, chunk algebra)

**What.** The exact classical primitives are implemented and committed:
DDT and LAT tables for all eight S-boxes, master-bit coverage of each
round key, the 2^8 completion enumeration, and last-round partial
decryption. Run `20261126T082618Z-5b997b4e-3f683965-s0`.

**Findings.** Differential uniformity is `16/64 = 0.25` (max DDT entry
excluding the trivial a=0 row); the largest non-trivial linear
correlation is `40/64 = 0.625`; one round key observes 48 master bits and
leaves 256 completions; two adjacent round keys already cover all 56
master bits. These are the ceiling numbers the SPADE residual must beat.

**Bug caught.** `SBOXES` is row-major, and the 6-bit S-box input is not a
flat index. The theory tests caught a wrong-answer lookup that the FIPS
vector alone did not expose; `sbox_output` is now the only lookup path
and has regression coverage (ADR-0005).

**Next.** Trail search and collision certificates (TH-1 remainder, #2),
then the SPADE scorer (#3, #4).

# Research log

Reverse chronological. One entry per decision or result; link the issue
and the manifest. Interpretations are provisional until replicated.

## 2026-11-26 — Design review: SPADE selected

**What.** Four independent designs (distinguisher + DDT ranking,
candidate-key refinement, measurement/probing, structure-informed) were
reviewed by three lenses (cryptanalysis, ML methodology, compute
feasibility). All three ranked the structure-informed arm first; its
grafts from the other arms are mandatory. The result is
[`ROADMAP.md`](ROADMAP.md) and [ADR-0008](adr/0008-research-strategy-spade.md).

**Why.** DES's last round decomposes into eight independent 64-way
subkey hypotheses, and the key schedule is GF(2)-linear, so the problem
is a 6-bit chunk density-ratio estimation with 2^8 master-key
completions — not a 56-bit regression. Initialising the scorer with the
exact DDT log-likelihood makes the neural contribution measurable as a
residual rather than a from-scratch classifier.

**Consequence.** The Stage 0 `PairCNN` is a baseline only. Stage 1 is
blocked on the SPADE modules (issue #4). Pre-registered F1–F6 are frozen
in ADR-0006 before any confirmatory run.

## 2026-11-26 — Repository bootstrap (Stage 0)

**What.** Created the project repository, governance (PR-only `main`,
seven blocking gates, advisory review agent), a bit-exact DES reference
and vectorised implementation, key-disjoint KPA/CPA data streams, a
trainable distinguisher, and result manifests.

**Why.** The previous 16-bit SPN result could not distinguish learning
from memorisation: no key-disjoint split, no budget-matched baseline,
no committed manifest. Stage 0 exists to make later claims auditable
before any DES claim is made.

**Evidence.** `results/stage0/<run_id>/manifest.json` (DES conformance).

**Open questions.**

- Does 4-round DES leave a learnable KPA signal at 6 GB of VRAM?
- At which round count does the advantage interval first include zero?
- Is the neural score aligned with a classical differential
  characteristic, or with something else?

## Prior stage — 16-bit SPN toy (archived)

The full write-up and figures are in
[`research/background/original-readme.md`](../research/background/original-readme.md).

**Claimed result.** 2-round, 16-bit SPN, exact key recovery in ~27% of
512 trials, versus ~0.2% for a uniform policy; 4 rounds did not train.

**Known limitations (retrospective).**

1. Target keys were sampled uniformly each step from a 2^16 space, so
   the "test" keys were almost certainly seen during training.
2. The uniform-policy baseline is not budget-matched random search.
3. At a 16-bit key, brute force costs 65,536 encryptions, which is
   orders of magnitude below the training cost; the result cannot be an
   attack, only a learning demonstration.
4. "SPN" and "Feistel" were used interchangeably for a single-branch
   substitution-permutation construction.

These limitations are the reason for the protocol in
[ADR-0002](../docs/adr/0002-experiment-protocol.md).
