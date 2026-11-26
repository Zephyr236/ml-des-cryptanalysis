# Experiment register

Source of truth for the design: [`ROADMAP.md`](ROADMAP.md) §4. Endpoints
and decision rules: [ADR-0006](adr/0006-pre-registered-endpoints.md).
Status legend: `planned` → `running` → `done` / `failed` / `censored`.

A `failed` or `censored` experiment stays in this table with its issue
and manifest. Deleting a failure is not allowed.

## Stage 0 — infrastructure and correctness

| ID | Deliverable | Gate | Status |
|---|---|---|---|
| INF-1 | PR-only `main`, required checks, issue-cleared merge, `AGENTS.md` | direct push rejected; protection verified | done |
| INF-2 | CI: lint, unit tests, conformance, manifest validation, ADR/link/release gates | green on the bootstrap PR | done |
| INF-3 | Claude Agent SDK review agent, advisory, files issues | agent comments and files a labelled issue | wired; key pending (#11) |
| INF-4 | Reference + vectorised DES, FIPS KAT, `10^6` cross-check | conformance manifest | done at 256-vector scale; `10^6` sweep pending |
| INF-5 | Key-schedule coverage map, inversion, 2^8 kernel assertion | assertions committed | planned (#4) |
| INF-6 | Host RAM/VRAM smoke run, manifest round-trip | GPU smoke manifest; peak RAM/VRAM logging still pending | GPU smoke done (`20261126T082618Z-5b997b4e-3f683965-s0`); memory counters pending (#10) |
| INF-7 | ADR-0001/0005/0006/0007 frozen, manifest schema, seed registry | ADR gate green | done |

**G0:** all KATs pass; throughput ≥ `10^7` blocks/s (target `5×10^7`);
memory smoke passes; a GPU job produces a committed manifest.

## Stage 1 — classical ceiling and distinguisher

| ID | R | Model | Primary metric | Status |
|---|---|---|---|---|
| TH-1 | 1–16 | exact DDT/LAT, beam trail search, Matsui linear | checksums; MC agreement | partial (#13: DDT/LAT + coverage; #43: beam trail search); Matsui linear pending (#2) |
| TH-2 | 2–16 | DP/collision certificate | `C_r`, `p_r`, implied N + CI | planned (#2) |
| TH-3 | 4–16 | predicted rank curves | predicted vs observed rank | planned (#2) |
| DG-4 | 4 | SPADE chunk scorer, CPA | chunk AUC vs log-DDT, ECE | planned (#3) |
| DG-6 | 6 | same | AUC | planned (#3) |
| DG-8 | 8 | same | AUC | planned (#3) |
| DG-10/12/14/16 | 10–16 | same, capped | AUC, bounds | planned (#9) |
| VA-2 | 1–16 | independent reference cross-check | bit-exact agreement | done at 64 samples; `10^6` pending |

**G1:** theory engine reproduces classical trail probabilities; DG-4 AUC
CI excludes 0.5; leak canary at chance. If DG-4 is at chance, diagnose
before any key-recovery run.

## DDT rank baseline (TH-3 partial, 2026-11-26)

Exact log-DDT scoring of all 64 last-round chunks, 128 key-disjoint test
keys x 64 pairs per key. The "one-bit delta" rows use CPA with
`delta = 0x0000000000000001`; KPA uses uniform random plaintexts. Mean
rank 32.5 and top-1 1/64 are chance.

| R | Mode | Mean rank | Top-1 | Run |
|---|---|---|---|---|
| 4 | CPA | 33.60 | 0.0146 | `20261126T084132Z-c72525e7-ab1bb162-s0` |
| 4 | KPA | 32.52 | 0.0127 | `20261126T084139Z-c72525e7-be5f91bb-s0` |
| 6 | CPA | 32.05 | 0.0195 | `20261126T084146Z-c72525e7-b03b4b73-s0` |
| 6 | KPA | 32.16 | 0.0176 | `20261126T084152Z-c72525e7-e5cedf94-s0` |
| 8 | CPA | 32.92 | 0.0127 | `20261126T084157Z-c72525e7-112b0abb-s0` |
| 8 | KPA | 32.41 | 0.0107 | `20261126T084202Z-c72525e7-e37489ed-s0` |

**Interpretation.** Unfiltered pairs and a one-bit delta carry no usable
last-round DDT signal at 64 pairs across R=4-8. This is not a refutation
of classical differential attacks: those select a high-probability
characteristic and keep right pairs. It establishes that TH-1 trail
selection and right-pair filtering are prerequisites for DG-4, not
optional refinements. The SPADE residual must be initialised from a real
characteristic, not from an arbitrary delta.

## TH-1 trail search (2026-11-26)

Beam search over all 64 single-bit start differences; `beam=8000`,
`branch=4`, `combos=12`; best **active** trail per round. Run
`20261126T135943Z-30b315b1-1cc32a1a-s0` on the RTX 2060 host. An earlier
run (`20261126T135117Z-fc37e176-f9c5d98f-s0`) produced identical
probabilities; the expanded run adds power, beam sensitivity and r=4
validation.

| Rounds | Active log2 p | Probability | Last-round S-box inputs | Validation |
|---|---|---|---|---|
| 1 | -2.000 | 0.25 | S6=8 | 0.25028, CI [0.2476, 0.2530], n=100k |
| 2 | -2.000 | 0.25 | S6=8 | 0.24907, CI [0.2479, 0.2503], n=500k |
| 3 | -7.093 | 0.00732 | S2=8, S8=8 | 0.007316, CI [0.007151, 0.007485], n=1M |
| 4 | -17.642 | 4.89e-6 | S3=5, S4=16, S7=7, S8=48 | 5.10e-6, CI [4.20e-6, 6.19e-6], n=20M |
| 5 | -27.694 | 4.60e-9 | S2=10, S3=32, S6=3, S7=52 | not sampled |

Prose uses 1-based S-box labels (S1..S8); `trails.json` stores 0-based array indices (index `k-1` for Sk). The r=1
overall `best` is a trivial probability-1 trail with no active S-box; it
is reported separately and is not used as a distinguisher.

### Power / pair budget

At the existing 64-pairs/key DDT budget, `N*p` is:

| Rounds | p | E[right pairs at 64] | Pairs for 10 | Pairs for 100 |
|---|---|---|---|---|
| 1 | 0.25 | 16 | 40 | 400 |
| 2 | 0.25 | 16 | 40 | 400 |
| 3 | 0.00732 | 0.469 | 1,366 | 13,654 |
| 4 | 4.89e-6 | 3.13e-4 | 2,045,223 | 20,452,226 |
| 5 | 4.60e-9 | 2.95e-7 | 2,171,874,821 | 21,718,748,203 |

**Corrected framing.** The r=3 trail is a candidate for a 4-round attack
only at roughly 1.4k–14k pairs/key, not at 64. The r=4 trail is a
candidate for a 5-round attack at roughly 2M–20M pairs/key (small-scale
only). The r=5 trail needs more than 2e9 pairs for 10 right pairs, so
R=6 is out of scope at this budget. The earlier "candidate" language
without these numbers was wrong.

### Beam sensitivity

The best-active log2 probability is identical at beams 500, 2000 and
8000 for every R=1..5. The lower bound is stable under beam width, but
branch/combos/start-set ablations and an exact/Matsui optimality
comparison remain follow-ups (issue #65).

## Stage 2 — key recovery

| ID | R | Pipeline | Primary metric | Status |
|---|---|---|---|---|
| VA-1 | — | DES-24/32 exhaustive rank validation | rank-estimator error, CI coverage | planned (#6) |
| KR-4 | 4 | chunk ranking → schedule decode → exact verify | success@1, rank, pairs-to-50% | planned (#5) |
| KR-6 | 6 | same, data sweep | success@1 vs q | planned (#5) |
| AB-1..3 | 4, 6 | DDT-init vs scratch; 8×64 vs 48/56-bit heads; soft vs argmax | delta success@1 | planned (#5) |
| CT-7 | 16 | full architecture negative control | all metrics at chance | planned (#9) |

**G2:** KR-4 passes; VA-1 passes; CT-7 at chance; every success verified
by re-encryption.

## Stage 3 — KPA vs CPA

| ID | R | Model | Primary metric | Status |
|---|---|---|---|---|
| KP-4..8 | 4–8 | LinScorer (Walsh/parity) primary; DiffScorer comparison | success@1, AUC vs linear counter | planned (#7) |
| AB-4 | 6, 8 | differential vs linear vs no prior | AUC | planned (#7) |
| PR-1 | 4–8 | representation probes (log-DP, support, active mask) | probe R²/AUC; shuffled null | planned (#7) |
| LG-1 | — | legitimacy audit; M2 cannot see K* | canary AUC CI includes 0.5 | planned (#7) |

**G3:** canary at chance; prior-match effect demonstrated; KPA/CPA gap
measured with CIs.

## Stage 4 — scaling to 16

| ID | R | Pipeline | Primary metric | Status |
|---|---|---|---|---|
| KR-8 | 8 | **primary endpoint F1** | success@1 diff vs classical (one-sided CI) | planned (#8) |
| KR-10..16 | 10–16 | capped probes | success@1, AUC, bounds | planned (#9) |
| KP-10..16 | 10–16 | capped probes | success@1, AUC, bounds | planned (#9) |
| CT-1..8 | all | control suite | null distributions | planned (#9) |
| AB-5..8 | 4–8 | relaxed core, oracle anneal, trails, corrected-bits-only | delta AUC/success | planned (#9) |

**G4:** F1 decision recorded (win or lose); `r*` with CI; censored runs
reported. A negative at R = 8 does not block Stage 5.

## Baseline note

The `configs/distinguisher/des{R}-{kpa,cpa}.yaml` files train the
unstructured `PairCNN`. They are **baselines and smoke tests**, not the
SPADE plan; see [ADR-0008](adr/0008-research-strategy-spade.md). SPADE
configs arrive with issue #4.
