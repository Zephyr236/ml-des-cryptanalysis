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
| TH-1 | 1–16 | exact DDT/LAT, branch-and-bound trails, Matsui linear | checksums; MC agreement | partial (#13, `20261126T082618Z-5b997b4e-3f683965-s0`): DDT/LAT + coverage; trail search pending (#2) |
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
