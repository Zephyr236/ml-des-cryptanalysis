# 研究路线图 / Research Roadmap

> **中文摘要（给研究者的 60 秒版本）**
>
> 1. **不再把密钥恢复当成 56-bit 回归问题。** DES 的最后一轮天然分解成 8 个
>    独立的 64 选 1 子密钥问题；密钥编排又是 GF(2) 线性的，恢复 48-bit 轮密钥
>    后只剩 2^8 = 256 个主密钥需要枚举验证。2^56 的搜索被降维成 6-bit 块上的
>    密度比估计。
> 2. **主方案是 SPADE**（Arm D）：S 盒分解的末轮打分器 + 用精确 DDT 初始化的
>    残差 + 精确密钥编排解码。A/B/C 三条备选路线的可取部分作为强制 graft 并入
>    （预注册否证、经典上界、校准、表示/解码诊断）。
> 3. **预期**：R=4/6 可以做出可验证的完整密钥恢复；R=8 是主终点，按同等总算力
>    与经典差分比较，结果很可能是负的；R=10–16 预期无信号，交付带置信区间的
>    负结果与 signal-death 轮数 `r*`。
> 4. **诚实边界**：16 轮即完整 DES，本项目不会、也不能"攻破 DES"；任何高轮数
>    的"成功"先按泄漏或评测 bug 处理。
> 5. **预注册否证 F1–F6** 写在 [ADR-0006](adr/0006-pre-registered-endpoints.md)，
>    主终点 F1 在跑之前冻结；负结果是一等交付物。
> 6. **12 周计划**：Stage 0 基础设施（当前）→ Stage 1 经典上界+区分器 →
>    Stage 2 密钥恢复 → Stage 3 KPA vs CPA → Stage 4 扩展到 16 轮 →
>    Stage 5 复现与成文。
>
> **本仓库的命名映射**：本文中的 `results/` 与仓库一致；CI 跑在 GitHub
> Actions（CPU smoke）而不是 2 GB 控制器上；真实训练在 `192.168.137.1` 的
> RTX 2060 上。ADR 编号映射：DES 约定 → 0005，预注册终点 → 0006，
> 数据划分与种子 → 0007，研究策略 → 0008。

---

# Machine-Learning KPA/CPA Key Recovery on Round-Reduced DES (R = 4–16) — Final Research Roadmap

**Version:** 1.0 · **Date:** 2026-11-26 · **Owner:** Research Lead
**Status:** Approved execution plan. Subordinate to the pre-registered ADRs once frozen.
**Governing artifacts:** `AGENTS.md`, ADR-0001 (governance/CI), ADR-0005 (DES conventions), ADR-0006 (pre-registered endpoints), ADR-0007 (data splits and seeds), ADR-0008 (research strategy).

---

## 1. Executive Summary and Honest Scope

### 1.1 What this project is

This is a controlled, pre-registered study of whether machine-learned statistics can extend differential/linear key recovery on real DES beyond what the exact classical statistics achieve, across round counts R = 4, 6, 8, 10, 12, 14, 16, under both chosen-plaintext (CPA) and known-plaintext (KPA) attack models.

The central design decision is that **key recovery is not posed as regression over the 56-bit key**. DES's public structure factors the problem exactly:

1. At the ciphertext end, the last round exposes an exact likelihood-ratio decomposition: after IP, `R_{R-1} = L_R` is known, the S-box input `E(L_R)[6j:6j+6] xor K_R[6j:6j+6]` is public up to a 6-bit chunk, and the packet input difference `E(L_R)_j xor E(L'_R)_j` is key-independent. The 48-bit last-round subkey therefore decomposes into **8 conditionally independent 64-way hypotheses**, each scored by partial decryption.
2. The DES key schedule is GF(2)-linear. Each round-key bit is a copy of exactly one master bit; one round key covers 48 of 56 master bits, leaving 8 free → **2^8 = 256 master key candidates**, each verified by exact re-encryption.

The 2^56 needle-in-a-haystack becomes a low-dimensional density-ratio estimation problem on 6-bit chunks, whose sample complexity is governed by S-box differential uniformity, not by key-space size. This is the answer to the researcher's open question: the 2-round toy cipher was exhaustive over a 2^16 key space; at 4 rounds the direct map fails because the key→ciphertext function behaves like a random function, not because a smooth function is missing.

### 1.2 What is likely achievable (calibrated expectations)

| Rounds | CPA expectation | KPA expectation | Claim class |
|---|---|---|---|
| 4 | Exact full-key recovery near-certain at modest data; matches classical differential at matched work | High success via linear/parity prior; lower than CPA | **Demonstrated result** |
| 6 | High success; comparison to classical is the scientific question | Moderate; classical linear baseline is strong | **Demonstrated result / boundary** |
| 8 | Primary endpoint. Chunk-level signal likely small; full-key success vs classical likely **negative** at feasible budgets | Chance-to-weak | **Confirmatory test (F1)** |
| 10 | Chunk AUC possibly marginally above 0.5; full key essentially 0 | Chance expected | **Boundary measurement** |
| 12–16 | Null expected; quantitative bound with CI | Null expected | **Negative result / certificate** |

The expected scientific contribution is a **methods-and-boundaries** result with (a) a measurable answer to "what does ML add over the exact DDT log-likelihood statistic?", (b) a pre-registered signal-death round `r*` with confidence interval, and (c) a rigorous negative at high rounds. A positive margin at R = 8 is possible but is not assumed anywhere in the plan; no decision gate depends on it.

### 1.3 What 16 rounds cannot deliver

- **No break of DES.** Best published attacks on full DES require on the order of 2^43 known or 2^47 chosen plaintexts (Matsui; Biham–Shamir — literature anchors to be re-verified, not quoted from memory). At the ≤ 2^26-pair cap this project can sustain, R = 14–16 cannot produce key recovery, and the roadmap says so before any experiment runs.
- **No "DES is broken" framing.** Any write-up must state data complexity, time complexity, and attack model explicitly, and must not generalize reduced-round results.
- **No claim that neural methods beat classical cryptanalysis at R ≥ 10.** If such a result appears at high rounds, the working assumption is leakage or an evaluation bug, and the pipeline's R = 16 negative control must be consulted before any claim is drafted.

### 1.4 Non-goals and wording rules

- No learned differentiable surrogate of DES in any headline experiment (the Gumbel-softmax `RelaxedCore` exists only as an ablation, AB-5).
- No full-key differential scoring (provably blind: `DP_r` is key-independent). All differential statistics rank **last-round chunks** by partial decryption.
- All success claims require exact re-encryption verification; model confidence is never evidence.
- Every report distinguishes "confirmed", "bound", and "speculation" in separate sections.

---

## 2. Chosen Architecture

### 2.1 Decision

**Base arm: Arm D — SPADE (Structure-Prior Attack on DES): S-box-factorized last-round scoring with a DDT-initialized residual and exact key-schedule decoding.** All three independent reviews ranked D first (totals 7.9, 8.4, 7.8). Grafts from Arms A, B, C are incorporated as specified in §2.4.

| Arm | Verdict | Decisive reason |
|---|---|---|
| **D — SPADE** | **Selected as base** | Only arm that combines correct cryptanalysis, guaranteed classical parity at initialization (g = 0 reproduces the DDT-weighted attack), exact schedule decoding, a real KPA path (linear/parity prior), and the lowest compute/memory footprint on the constrained hardware |
| A — distinguisher + DDT ranking | Graft source | Rigorous pre-registration, but single-S-box isolation changes only 4 of 64 ciphertext bits per candidate, structurally starving the network of candidate-dependent leverage; headline margin likely null |
| B — key-refinement scorer | Graft source | Fatal search-distribution shift: at Hamming distance ~28 the residual `Q_delta` is statistically uniform, so the potential is flat exactly where beam search must start; DAgger cannot manufacture absent signal; highest compute and leakage surface |
| C — measurement/probing study | Graft source | Best-in-class statistical discipline (r* certificate, DES-24 validation, representation/decoder separation) but explicitly not an attack; delivers key recovery only at R ≈ 4–6 |

### 2.2 Load-bearing structural facts (all verified against FIPS 46-3 tables in Stage 0)

1. `L_{R-1} = R_R xor P(S(E(L_R) xor K_R))` under the fixed no-final-swap convention; `R_{R-1} = L_R` known.
2. The pair input difference `a_j = E(L_R)_j xor E(L'_R)_j` is key-independent (round key cancels).
3. One round key selects 48 distinct master bits (PC-2 is a bit-selection map); 8 master bits are absent from `K_R` → hard decoding gives 2^8 completions.
4. **Correction accepted from review:** the claim that "any two adjacent round keys cover all 56 master bits" is not assumed. Master-bit coverage of any set of recovered round keys is **computed exactly from PC-1/PC-2/rotation tables** at runtime and asserted; soft decoding sums master-bit log-odds over all observed occurrences and enumerates any uncovered bits. The 2^96 candidate-pair count claim from Arm D is withdrawn.
5. DDT statistics are aggregated as **log-likelihood** `log P(b | a) = log(DDT_j[a][b] / 2^6)`, not as a single-trail match count — this is the honest Neyman–Pearson comparator and the headline baseline (F2 is defined against it).

### 2.3 Module specification (M1–M8)

| Module | Learned? | Function |
|---|---|---|
| **M1 exact_des** | No | Bitsliced DES (C++/numpy bit-packing) on CPU, R rounds; all states and round keys exposed; reference pure-Python implementation for cross-checks; key-schedule inversion and exact verifier. Target ≥ 5×10^7 blocks/s bitsliced; hard floor 10^7/s with GPU fallback |
| **M2 FeatureExtractor** | No | Per (pair, S-box): `x_j, x'_j, a_j` (6 bits each), `R_R, R'_R`, observed 64-bit ΔP, top-k (k = 16) public trail-compatibility log-scores, expected `b*` masks. Interface **physically cannot see K***. LinScorer variant replaces ΔP features with per-S-box Walsh/parity sums |
| **M3 ChunkScorer g_θ** | Yes (~0.35M params) | Shared trunk over 96-d features + round/S-box embeddings; 3 residual blocks (Linear 112→256, LayerNorm, GELU, Dropout 0.1); 64-way head. 64 candidates share the trunk (candidate enters via `u = x_j xor c`), so the trunk runs once per (pair, S-box). **DDT-init:** fixed additive term `log DDT_j[a_j][b(c)]` (ε-smoothed at 2^-8 for zero entries), so g = 0 is exactly the classical DDT-weighted attack |
| **M4 PairContextEncoder** | Yes (~0.4M, optional) | 2-layer transformer over m pair tokens; tests cross-pair structure beyond sum pooling |
| **M5 DeepSetsPool** | No | Sum (not mean) of per-pair logits over m → `[B, 8, 64]`; sum is the correct log-likelihood aggregation and preserves data-complexity scaling |
| **M6 ScheduleDecoder** | No | Precomputed master-bit coverage map; round-key-bit log-odds → master-bit log-odds (soft repetition decode); top-K enumeration over least-confident/uncovered bits; hard mode enumerates the exact 2^8 completions |
| **M7 Verifier** | No | Exact re-encryption of held-out pairs; only accepted success; counts oracle queries, pairs, and key trials for budget matching |
| **M8 RelaxedCore** | Yes (ablation only) | Gumbel-softmax S-box relaxation, annealed 1.0 → 0.01; used only in AB-5; final features always recomputed exactly |

Total parameters < 1M (≈ 4 MB fp16); activations at B = 256, m = 64, 8 S-boxes, 64 logits ≈ 34 MB; peak VRAM < 2 GB.

### 2.4 Grafted elements (mandatory, not optional)

| Source | Graft | Where it lands |
|---|---|---|
| A | Pre-registered falsifiers F1–F6 (below) and primary endpoint fixed in ADR-0006 before confirmatory runs | Stage 0 / ADR-0006 |
| A | Temperature scaling on held-out keys + **ECE ≤ 0.10 gate**; reliability curves; paired bootstrap on identical keys/pairs; Holm correction over the 56 (R, S-box) cells | §5, Stage 1/4 |
| A | Corrected-bits-only ablation (AB-7, "learned DDT"), wrong-α control (CT-5), permuted-P control (CT-6), R = 16 negative-control round (CT-7) | Control suite |
| A | Equal-compute accounting: FLOPs and wall-clock for scorer and every classical baseline | §5.6 |
| B | Set-level listwise 64-way softmax CE over sum-pooled logits (train objective = inference objective); distance-ordered margin term; far-negative curriculum for candidate pools | Training protocol §2.6 |
| B | `KL(Q_delta ‖ U)` / collision-probability pre-computation: before training any (R, q) cell, estimate the available signal and pre-register a null if below the detection threshold | TH-2/TH-3 |
| B | Exact GF(2) linear solve as a cross-check on M6 | Stage 2 |
| C | Classical ceiling engine first (exact DDT/LAT, branch-and-bound trails, multi-trail/truncated sets, Matsui linear); every neural score calibrated against the strongest classical statistic | TH-1, Stage 1 |
| C | Pre-registered signal-death round `r*` with 95% CI + collision certificate `N(2^64 C_r − 1)` and `N·p_r` | Stage 4 |
| C | Representation/decoder probe suite with shuffled-target nulls and linear-vs-MLP capacity curves | Stage 3 |
| C | DES-24/DES-32 exhaustive-rank validation as a hard gate before any 2^48/2^56 rank claim | VA-1, Stage 2 |
| C | Random-S-box and random-Feistel structural nulls calibrated at R = 4; 1% deterministic replay | CT-1/CT-2, CT-8 |

### 2.5 Mandatory corrections accepted from review

1. **Key-schedule claims:** only the verified facts (48 selected bits per round key; 2^8 kernel) are used. Multi-round coverage is computed, not asserted.
2. **No-oracle confirmatory mode:** the curriculum's oracle active-S-box mask and expected-`b*` teacher forcing are annealed to exactly zero; all headline numbers are produced with **zero oracle features**. Oracle-mode results are reported separately as upper bounds.
3. **Headline baseline is log-DDT aggregation**, not single-trail match count. F2 is defined against the log-DDT counter.
4. **R = 8 endpoint reframed** (review consensus): primary is *match or beat budget-matched classical differential at equal total work, and beat the log-DDT counter at equal data*; full-key success at q ≤ 2^24 is a bonus, not the endpoint.
5. **Host-RAM smoke test is an existential Stage 0 gate**; `num_workers = 0` is mandatory (Arm D's "≤ 2 workers" allowance is withdrawn).
6. **CI on the 2 GB box is torch-free**: pure-Python/numpy DES, schema validation, ADR gate, reviewer agent only.

### 2.6 Loss, aggregation, decoding

- **Stage A (per-pair):** `L_A = CE_64(logits, true chunk)` separately for each of 8 S-boxes, with DDT-init active; auxiliary `Brier` calibration term; optional distance-ordered margin over wrong chunks.
- **Stage B (set/listwise):** `L_B = CE_64(sum-pooled logits over m pairs, true chunk)` per S-box — this *is* the inference objective (the InfoNCE graft in factorized form). Candidate pools for margin terms use the distance curriculum {1, 2, 4, random} with labels; distance regression is auxiliary only (leakage-adjacent) and is reported with a shuffle control.
- **Decoding:** sum-pool → per-chunk posterior → master-bit log-odds → top-K enumeration / exact 2^8 completions → exact verification. Soft and hard decoding are separate ablations (AB-3).
- **Numerics:** DDT log term floored at log(2^-8); final reductions in float64.

---

## 3. Staged Plan

### Stage 0 — Infrastructure and correctness gates (weeks 1–2)

**Objective:** every later number is produced by code that has passed hard correctness, memory, and governance gates.

| ID | Deliverable | Gate |
|---|---|---|
| INF-1 | Repo created; `main` protected (PR-only, no direct push); required checks; issue-cleared merge rule; `AGENTS.md` | Branch protection verified by a rejected direct-push test |
| INF-2 | CI on the 2 GB Linux box: lint, torch-free unit tests, manifest JSON-Schema validation, ADR gate via `delivery-gates` on watched paths | Green CI on a trivial PR (M0 exit) |
| INF-3 | Claude Agent SDK reviewer agent: reviews diffs, files GitHub issues with severity labels; cannot block directly, but merge rule requires all linked issues closed | Agent files a test issue and it appears in the PR checks |
| INF-4 | `exact_des` bitsliced CPU implementation + independent pure-Python reference | FIPS 46-3 KATs (incl. key `0x133457799BBCDFF1`, PT `0x0123456789ABCDEF` → `0x85E813540F0AB405`); complementation identity; round-trip decrypt; 10^6 random-vector cross-check for every R |
| INF-5 | Key-schedule coverage map computed from tables; inversion + verifier | Assertions: 48 distinct bits/round key; 2^8 kernel; exact master-bit coverage table committed |
| INF-6 | Host-RAM/VRAM smoke test: 10k-step training run on the Windows box over SSH; manifest emitted | Peak host RAM < 1.5 GB, VRAM < 2.5 GB, manifest round-trips through CI schema check |
| INF-7 | ADR-0001/0005/0006/0007 frozen; run-manifest schema; seed registry | ADR gate passes; F1–F6 text frozen |

**Go/no-go G0:** all KATs pass; throughput ≥ 10^7 blocks/s (target 5×10^7); memory smoke passes; SSH GPU job produces a committed manifest. **If the host cannot sustain a 10k-step run, escalate as a hardware blocker before committing any GPU-hours.**

### Stage 1 — Classical ceiling and round-reduced distinguisher (weeks 3–4)

**Objective:** know the ceiling before measuring the learner.

| ID | Experiment | Metric | Gate |
|---|---|---|---|
| TH-1 | Exact DDT/LAT; branch-and-bound trail search R = 1–16; multi-trail and truncated sets; Matsui linear search | Checksums; Monte-Carlo agreement for r ≤ 3; independent implementation agreement | Errors within CI; tables committed |
| TH-2 | DP/collision estimation (2^26–2^30 sampled pairs at low R; hashed histograms); `C_r`, `p_r`, implied `N` for advantage | Collision probability with 95% CI; bounds at high R | Certificate emitted per R |
| TH-3 | Predicted rank curve: `n·p_r` vs `sqrt(n·q_r)`; pre-registered null decisions | Predicted vs observed rank at R = 4, 6 | Calibrated on R = 4 |
| DG-4..DG-8 | ScoreNet (CPA, fixed Δ from best public trail; random-Δ twin) at R = 4, 6, 8 | Chunk AUC vs log-DDT counter; ECE after temperature scaling | AUC CI excludes 0.5 at R = 4; otherwise diagnose before proceeding |
| VA-2 | Independent reference cross-check at scale | 10^6 vector agreement | Hard gate |

**Go/no-go G1:** theory engine reproduces classical trail probabilities; DG-4 shows signal with CI excluding 0.5; leakage probe (CT-4) at chance. If DG-4 is at chance, stop and diagnose (bug vs signal) — do not proceed to key recovery.

### Stage 2 — Key recovery (weeks 5–6)

**Objective:** end-to-end exact master-key recovery at R = 4 and 6, with the decoding machinery validated against exhaustive ground truth.

| ID | Experiment | Metric | Gate |
|---|---|---|---|
| VA-1 | DES-24/DES-32 truncated-key variants; exhaustive rank and calibration ground truth | Rank-estimator error; CI coverage; calibration vs exact | **Hard gate:** coverage inside stated CI before any 2^48/2^56 rank claim |
| KR-4 | CPA, full pipeline: chunk ranking → schedule decode → exact verify | success@1, median rank, pairs-to-50%, vs classical at matched total work | success@1 ≥ 0.9 at feasible q; else bug investigation |
| KR-6 | CPA, same pipeline, data sweep | success@1 vs q; chunk accuracy | Match or beat recomputed classical data complexity within factor 2 |
| AB-1..AB-3 | DDT-init vs scratch; 8×64 vs 48-bit vs 56-bit heads; soft vs argmax decode | Delta success@1 at equal compute | DDT-init and factorization must win; otherwise record honestly |
| CT-7 | R = 16 full architecture negative control | All metrics at chance | Any success halts claims and opens a bug issue |

**Go/no-go G2:** KR-4 passes; VA-1 passes; CT-7 at chance; every success verified by re-encryption and triples stored.

### Stage 3 — KPA vs CPA (weeks 6–7)

**Objective:** run both attack models with model-matched priors and enforce the legitimacy ledger.

| ID | Experiment | Metric | Gate |
|---|---|---|---|
| KP-4..KP-8 | LinScorer (Walsh/parity) primary; DiffScorer conditioned on observed ΔP as comparison | success@1; chunk AUC vs classical linear counter | KP-4 high; KP-6 moderate; KP-8 chance-to-weak |
| AB-4 | Differential vs linear/Walsh vs no prior (D13) | AUC and success@1 at fixed m | Prior-match effect must appear; if differential prior works under KPA, suspect leakage |
| PR-1 | Representation probes: frozen encoder → true log-DP, top-k differential support, active-S-box mask; shuffled-target nulls; linear vs MLP capacity curve | Probe R²/AUC vs oracle; probe-vs-head gap | Leakage-safe targets only; shuffled null at chance |
| LG-1 | Legitimacy audit: M2 interface cannot see K*; leak-canary AUC CI includes 0.5 | Canary AUC | Hard gate; failure rejects the feature set |

**Go/no-go G3:** canary at chance; prior-match effect demonstrated; KPA/CPA gap measured with CIs.

### Stage 4 — Scaling to 16 (weeks 7–10)

**Objective:** the confirmatory test at R = 8 and the boundary map at R = 10–16.

| ID | Experiment | Metric | Gate |
|---|---|---|---|
| KR-8 | **Primary endpoint (F1):** CPA, q ≤ 2^24 on 64 keys + 2^18–2^22 sweep on 256 keys; matched-total-work classical differential | success@1 difference (one-sided 95% CI); chunk AUC vs log-DDT; bit accuracy | F1 decided and recorded in the PR before write-up |
| DG-10..DG-16 | Distinguisher rows | AUC vs log-DDT; ECE | Reported with CIs; no claim above chance |
| KR-10..KR-16, KP-10..KP-16 | Capped probes: 2^22 pairs/key × 128 keys; bounds, not point estimates | success@1, chunk AUC, bit accuracy, rank | Nulls reported with power analysis; `r*` estimated with 95% CI |
| CT-1..CT-8 | Full control suite (shuffled S-box, random Feistel, label shuffle, wrong-α, permuted P, canary, negative-control round, 1% replay) | All parent metrics; null distributions | Any deviation halts the corresponding claim |
| AB-5..AB-8 | RelaxedCore vs exact features; oracle-annealing check; mixture-of-trails on/off; correction-only head | Delta AUC/success | Recorded; RelaxedCore must not win at equal compute (else T3 is false and reported) |

**Go/no-go G4:** F1 decision recorded (win or lose); `r*` with CI; all censored runs reported. A negative at R = 8 is a valid deliverable and does not block Stage 5.

### Stage 5 — Analysis and write-up (weeks 10–12)

**Objective:** reproducible, honestly scoped final report.

- **EX-5.1 Replay:** two randomly chosen headline runs re-executed on a clean checkout from manifests only; metrics within stated tolerance; failures documented.
- **EX-5.2 Final statistics:** 5-seed (R ≤ 8) / 3-seed (R ≥ 10) aggregation; paired bootstrap; Holm correction; calibration plots.
- **EX-5.3 Report:** confirmed results / bounds / speculation in separate sections; data and time complexity stated per claim; explicit "no claim about full DES".
- **EX-5.4 Artifact bundle:** code, ADRs, manifests, metrics, figures; CI replays manifest schema and unit tests.
- **Gate G5:** report cross-check script confirms no statement contradicts committed `metrics.json` or F1–F6; every issue closed; final PR merged.

---

## 4. Experiment Matrix

All rows: keyed-hash (SplitMix64, ADR-0007) key-disjoint splits; seeds 0–4 (R ≤ 8) or 0–2 (R ≥ 10); exact re-encryption verification. "Pairs" are per key unless stated; CPA queries and pairs are both recorded and converted by the oracle-accounting function.

| ID | Stage | R | Model | Objective | Budget (planning) | Primary metric | Expected outcome |
|---|---|---|---|---|---|---|---|
| TH-1 | 1 | 1–16 | — | DDT/LAT, trails, linear search | exact tables | Checksums, MC agreement | Pass; ceiling tables |
| TH-2 | 1 | 2–16 | — | DP/collision certificate | 2^26–2^30 pairs | `C_r`, `p_r`, implied N, CI | r ≤ 4 agrees with theory; r ≥ 8 bounds |
| TH-3 | 1 | 4–16 | — | Predicted rank curves | none | Predicted vs observed rank | Calibrated at R = 4 |
| DG-4 | 1 | 4 | CPA | Chunk AUC vs log-DDT | 2^24 pairs | AUC, ECE | Clearly above 0.5 |
| DG-6 | 1 | 6 | CPA | Same | 2^24 | AUC | Small margin |
| DG-8 | 1 | 8 | CPA | Same | 2^24 | AUC | Near 0.5 |
| DG-10/12/14/16 | 4 | 10–16 | CPA | Same | 2^24–2^26 cap | AUC | Chance; bounds |
| KR-4 | 2 | 4 | CPA | Exact full-key recovery | q ≤ 2^12–2^14; 1000 keys | success@1, rank, pairs-to-50% | ≥ 0.9 at feasible q |
| KR-6 | 2 | 6 | CPA | Exact recovery + data sweep | q ≤ 2^16; 1000 keys | success@1 vs q | High; classical-matched within 2× |
| **KR-8** | **4** | **8** | **CPA** | **F1 primary: beat classical at matched work / beat log-DDT at matched data** | **q ≤ 2^24 on 64 keys + sweep on 256** | **success@1 diff (1-sided CI); AUC** | **Likely negative vs classical; small AUC margin at best** |
| KR-10 | 4 | 10 | CPA | Boundary probe | 2^22 × 128 keys | success@1, AUC, bit acc | ~0 success; AUC ≈ 0.5 |
| KR-12/14/16 | 4 | 12–16 | CPA | Boundary probe | 2^22 × 128 keys | success@1, AUC | Null with CI; explicit bound |
| KP-4 | 3 | 4 | KPA | Linear/parity recovery | m ≤ 2^14–2^16; 1000 keys | success@1, AUC vs linear counter | High via LinScorer |
| KP-6 | 3 | 6 | KPA | Same | m ≤ 2^18; 500 keys | success@1 | Moderate; below CPA |
| KP-8 | 4 | 8 | KPA | Same | m ≤ 2^22; 256 keys | success@1, AUC | Chance-to-weak |
| KP-10/12/14/16 | 4 | 10–16 | KPA | Boundary probe | 2^22 × 128 keys | success@1, AUC | Chance; bounds |
| AB-1 | 2 | 4, 6 | CPA | DDT-init vs scratch | matched | Delta success@1 | DDT-init wins |
| AB-2 | 2 | 6, 8 | CPA | 8×64 vs 48-bit vs 56-bit heads | matched | success@1; pairs-to-50% | Factorized wins by large margin |
| AB-3 | 2 | 6, 8 | CPA | Soft schedule decode vs argmax | matched, low-data | success@1, rank | Soft wins at low m |
| AB-4 | 3 | 6, 8 | KPA+CPA | Differential vs linear vs no prior | matched | AUC | Prior-match effect |
| AB-5 | 4 | 4, 6 | CPA | Exact features vs RelaxedCore | matched FLOPs | AUC | Exact ≥ RelaxedCore (tests T3) |
| AB-6 | 4 | 6 | CPA | Zero-oracle confirmatory check | matched | Delta success@1 vs oracle mode | Oracle gain quantified; headline = zero-oracle |
| AB-7 | 4 | 6 | CPA | Corrected-bits-only head ("learned DDT") | matched | success@1 | Collapses to DDT level |
| AB-8 | 4 | 8 | CPA | Mixture-of-trails features on/off | matched | AUC | Small or null; reported |
| CT-1 | 4 | 4–8 | both | Shuffled-S-box DES | matched | All parent metrics | Chance; DES S-boxes must dominate |
| CT-2 | 4 | 4–8 | both | Random Feistel, matched wiring | matched | All parent metrics | Chance; calibrated at R = 4 |
| CT-3 | 4 | 4–8 | both | Label shuffle | matched | success@1 | 1/64 |
| CT-4 | 4 | all | both | Leak-canary probe to K* | 10^5 pairs | AUC | CI includes 0.5; else reject features |
| CT-5 | 4 | 4–8 | CPA | Wrong/random α | matched | AUC | Signal tracks characteristic quality |
| CT-6 | 4 | 4–8 | both | P replaced by fixed random permutation | matched | AUC | Learned advantage vanishes |
| CT-7 | 2,4 | 16 | both | Full architecture negative control | matched | All metrics | Chance; else halt all claims |
| CT-8 | 5 | all | both | 1% deterministic replay | 1% of runs | Bit-exact metric reproduction | Pass |
| VA-1 | 2 | — | — | DES-24/32 exhaustive rank validation | all 2^24 keys | Estimator error, CI coverage | Hard gate before high-dim rank claims |
| VA-2 | 0–1 | 1–16 | — | Independent reference cross-check | 10^6 vectors | Bit-exact agreement | Hard gate |
| PR-1 | 3 | 4–8 | CPA | Representation probes (log-DP, support, active mask) | 2^22 activations | Probe R²/AUC; shuffled null | Tracks oracle where signal exists |

**Pre-registered falsifiers (frozen in ADR-0006):**

- **F1 (primary):** at R = 8, CPA, matched total work, the one-sided 95% CI lower bound on (ML success@1 − classical differential success@1) ≤ 0 → claim "ML extends differential key recovery at R = 8" is dead.
- **F2:** the DDT-init residual's chunk AUC does not exceed the log-DDT counter by the pre-registered margin (ΔAUC ≥ 0.02 or ≥ 2× fewer pairs to 50% chunk top-1) at any R ∈ {6, 8, 10} → "learning adds nothing beyond the differential distribution" conclusion.
- **F3:** shuffled-S-box control matches DES-S-box performance → the effect is not DES-structural; claim invalid.
- **F4:** leak-canary above chance, or the R = 16 negative control succeeds → evaluation bug; all claims halted pending investigation.
- **F5:** ECE > 0.10 after temperature scaling → no posterior/LLR-based claim is made.
- **F6:** a headline cell fails clean-checkout replay within tolerance → the claim is withdrawn or restated as non-reproducible.

---

## 5. Statistical Protocol

### 5.1 Splits
- Master keys assigned by a committed SplitMix64 hash of the 56-bit effective key with a fixed salt (ADR-0007; SHA-256 defines the reference construction but is too slow for GPU-side rejection sampling). The split function is versioned; CI asserts zero train/test key overlap before any manifest is accepted.
- A contiguous key-range holdout is reported as an extrapolation stress test; weak/semi-weak keys excluded from the main split and reported separately.
- Plaintexts and keys drawn from independent GPU-side RNG streams; generator version + seeds in every manifest.

### 5.2 Seeds and runs
- Seeds 0–4 for R ≤ 8; seeds 0–2 for R ≥ 10; fixed before runs. Every run in the registry is reported, including failures and censored runs (wall-clock cap hit → censored, not dropped).

### 5.3 Estimators and intervals
- success@1 and rank: bootstrap over **test keys** (10,000 resamples).
- AUC and calibration: bootstrap over seeds; paired bootstrap vs baselines on identical (key, pair) sets.
- Rank estimator validated exhaustively on DES-24 (VA-1) before any 2^48/2^56 claim.
- Power analysis reported for every null: minimum detectable effect at the stated n.

### 5.4 Multiple comparisons
- Primary endpoint F1: single, one-sided α = 0.05, no correction.
- F2 family: Holm–Bonferroni over 7 rounds × 8 S-boxes = 56 cells.
- All secondary endpoints declared before runs; hierarchical reporting order fixed (confirmatory → secondary → exploratory).

### 5.5 Calibration
- Temperature scaling fit on validation keys only; ECE and reliability curves reported; F5 gate. Sum-pooled logits are used as LLRs only after the gate passes.

### 5.6 Baselines and budget matching
- Uniform random search; classical differential (single-trail and log-DDT); multi-trail/truncated; Matsui linear; Gohr-style unstructured pair MLP; Benamira-style hand-feature model; direct key-map network (the researcher's prior pipeline, null control).
- Budget matched on total work = oracle queries + (key trials × pairs per trial) + verifier encryptions; FLOPs and wall-clock reported for every method.

### 5.7 Controls
See CT-1..CT-8. Automated "control-must-be-chance" tests run in CI on committed control metrics; a failing control opens a blocking issue for the linked claim.

---

## 6. Compute Budget and Wall-Clock

Target machine: RTX 2060 (6 GB), i7-10750H, 16 GB host RAM with 0.5–1 GB free at times. The 2 GB Linux box runs git/CI only and never trains.

### 6.1 Per-run cost
- Training step: B = 256 keys × m = 64 pairs × 8 S-boxes = 131k tokens; ~0.17 MFLOP/token → ~2.2×10^10 FLOP/step; ~8–15 ms/step at ~40% of 6.5 TFLOPS including generation; 100k steps ≈ 20–40 min; worst case < 60 min.
- Inference: trunk once per (pair, S-box); ~1.4 MFLOP/pair; dominated by evaluation sweeps, budgeted below.

### 6.2 Budget by stage

| Stage | GPU-hours | CPU-hours (bitsliced) | Notes |
|---|---|---|---|
| 0 Infrastructure | 0 | 10–20 | KATs, cross-checks, smoke tests |
| 1 Theory + distinguisher | 25–40 | 20–40 | TH-1..3, DG-4..8, VA-2 |
| 2 Key recovery R = 4, 6 | 35–50 | 10–20 | KR-4/6, ablations, VA-1, CT-7 |
| 3 KPA vs CPA | 20–30 | 10–15 | KP-4..8, probes, legitimacy |
| 4 Scaling R = 8–16 | 60–90 | 30–50 | KR-8 primary, capped probes, full controls |
| 5 Replay/write-up | 10–15 | 5–10 | Clean-checkout replay |
| **Total** | **150–225 (plan 190)** | **85–155** | +20% contingency ≈ 230 GPU-h |

At 8 h/day weekdays + 12 h/day weekends (~64 h/week), 12 weeks provide ~760 GPU-hours of capacity; the plan uses ~25% of it, leaving headroom for contention and reruns.

### 6.3 Memory and storage
- VRAM ≤ 2.5 GB (headroom to 5 GB cap); host RAM peak < 1.5 GB enforced by smoke test; `num_workers = 0`.
- Disk < 2 GB (manifests, compact metrics, trail tables); no raw corpora stored; checkpoints < 20 MB.
- Wall-clock risk buffer: 30% contingency per stage; checkpoints every 15 min; resume from manifest seed.

---

## 7. Repo/CI Mapping

Governance per the user's requirements: PR-only `main`, no direct pushes, all issues resolved before merge, CI gates, ADR gate via [delivery-gates](https://github.com/chohan-sarmad-ali/delivery-gates), Claude Agent SDK reviewer that files issues but has no direct merge authority.

### 7.1 CI jobs (2 GB Linux box; torch-free)

| Job | Trigger | Checks | Blocks merge? |
|---|---|---|---|
| `lint` | every PR | ruff/format | Yes |
| `unit-tests` | every PR | pure-Python/numpy DES KATs, key-schedule coverage assertions, manifest schema round-trip, metric-code unit tests | Yes |
| `manifest-schema` | PRs touching `results/` | JSON Schema validation of every committed manifest + metrics | Yes |
| `split-overlap` | PRs touching splits/data code | Recomputes split hashes; asserts zero test/train key overlap | Yes |
| `adr-gate` | PRs touching watched paths (crypto core, splits, metric code, trail/alpha data, schedule inversion, endpoint definitions) | `delivery-gates` check requires linked ADR | Yes |
| `control-audit` | PRs with control metrics | Automated "must be at chance" assertions for CT rows | Yes |
| `report-crosscheck` | PRs touching report/figures | Script asserts no statement contradicts `metrics.json` or F1–F6 | Yes |
| `reviewer-agent` | every PR | Claude Agent SDK reads diff, posts review comment, files issues with severity labels | Indirect: issue-cleared rule blocks merge |
| `issue-cleared` | merge | GitHub API query: all linked issues closed/labeled resolved | Yes |
| GPU execution | manual dispatch | Runs on the Windows box over SSH; copies manifests/metrics back; no training on CI | N/A (produces artifacts) |

### 7.2 Artifact-by-stage map

| Stage | Committed artifact | Produced on | Verifying gate |
|---|---|---|---|
| 0 | `des/`, `tests/`, `schemas/`, `.github/workflows/`, ADR-0001..0008, `AGENTS.md` | Linux + Windows (smoke) | `unit-tests`, `adr-gate`, smoke manifest |
| 1 | `theory/` tables, `trails.json`, DG manifests/metrics | Windows GPU (via SSH) | `manifest-schema`, TH recompute test |
| 2 | KR manifests, success triples hash, VA-1 report | Windows GPU | `manifest-schema`, verifier re-check of sampled triples |
| 3 | KP manifests, probe results, legitimacy audit | Windows GPU | `control-audit`, leak-canary gate |
| 4 | F1 decision record, boundary tables, control suite results | Windows GPU | `report-crosscheck`, `control-audit` |
| 5 | Final report, figures, replay logs | Mixed | `report-crosscheck`, replay reproduction |

Every GPU result enters the repo only through a PR carrying `run_manifest.json` (git SHA, config hash, seed, split hash, R, model, budgets, GPU/driver/torch versions, wall-clock, peak VRAM/RAM) and `metrics.json`.

---

## 8. Risk Register

| # | Risk | L | I | Mitigation | Trigger |
|---|---|---|---|---|---|
| 1 | Host RAM (~0.5–1 GB free) cannot sustain PyTorch + CUDA context | M | Critical | Mandatory INF-6 smoke test < 1.5 GB; workers=0; on-GPU generation; reduce batch before width; escrow a reduced config | Smoke test fails → hardware escalation before GPU-hours |
| 2 | No ML margin over log-DDT (Benamira outcome) | H | Medium | Expected and pre-registered; DDT-init design makes the answer measurable; negative is a deliverable | F2 fires → boundary paper |
| 3 | R = 8 primary endpoint negative | H | Low | Reframed endpoint; F1 pre-registered; R ≤ 6 results still stand | F1 fires → record and proceed |
| 4 | Silent DES table/bit-order bugs | M | Critical | Dual implementations, FIPS KATs, 10^6 cross-check, CI gate, CT-7 | Any mismatch → halt |
| 5 | Leakage through features or splits | M | Critical | M2 interface cannot see K*; split hashes in CI; canary; label shuffle; reviewer audit | Canary above chance → reject features |
| 6 | Rank estimator bias at 2^48/2^56 | M | High | DES-24 exhaustive validation as hard gate; stratified sampling | VA-1 coverage fails → no rank claims |
| 7 | Teacher-forcing contamination of the ML-gain claim | M | High | Anneal to exactly zero; all headline numbers zero-oracle; oracle mode reported separately | AB-6 shows residual oracle dependence |
| 8 | Bitsliced throughput below plan | M | Medium | Benchmark in Stage 0; GPU fallback; scope cut by pre-registered rule, applied uniformly to all methods | < 10^7 blocks/s |
| 9 | Reviewer-agent issue churn delays merges | M | Low | Severity labels + triage; issue-cleared rule scoped to linked issues; reviewer cannot block directly | Merge queue stall > 3 days |
| 10 | SSH/Windows setup blocks GPU access | M | High | INF-1/INF-6 gate; OpenSSH Server + firewall checklist; fallback: local scheduled runs with manual manifest commits | SSH job fails at M0 |
| 11 | Compute overrun in evaluation sweeps | M | Medium | Pre-registered caps (2^22 × 128 keys at R ≥ 10); uniform trimming across methods, never baselines only | Mid-stage burn > 130% of plan |
| 12 | Novelty already published | L | Medium | Phase-0 literature survey in Stage 0; claim scoped to factorization + schedule decoding + matched comparison | Survey finds prior art → rescope claims |
| 13 | Overclaiming in write-up | M | High | Report-crosscheck CI; confirmed/bounds/speculation separation; explicit no-DES-break statement | Crosscheck failure blocks PR |
| 14 | Null at high rounds read as project failure | M | Medium | Pre-registered framing; r* certificate; representation/decoder 2×2 as the deliverable | Reviewer/reader confusion → point to ADR-0006 |

---

## 9. Twelve-Week Milestone Schedule

| Week | Milestone | Work | Exit gate |
|---|---|---|---|
| 1 | **M0a** repo/governance | INF-1..3, INF-7; branch protection; CI skeleton; reviewer agent | Direct push rejected; trivial PR green |
| 2 | **M0b** correctness + hardware | INF-4..6; KATs; coverage map; RAM smoke; throughput benchmark | **G0 passes** |
| 3 | **M1** theory engine | TH-1, TH-2; ADR-0006 endpoints frozen; trail database | Theory errors within CI |
| 4 | **M2** distinguisher | DG-4..DG-8; calibration; CT-4 canary | **G1: DG-4 AUC CI excludes 0.5** |
| 5 | **M3** key recovery | KR-4; AB-1..3; VA-1 validation | KR-4 success; VA-1 coverage |
| 6 | **M4** R = 6 + controls | KR-6 sweep; CT-7; DES-24 report | **G2: R = 4/6 exact recovery verified** |
| 7 | **M5** KPA track | KP-4..KP-8; AB-4; PR-1 probes; legitimacy audit | **G3: canary at chance; prior effect shown** |
| 8 | **M6** R = 8 primary | KR-8 (F1); full controls; mixture ablation | F1 decision recorded |
| 9 | **M7** boundary map | KR/KP 10–16 capped probes; r* estimate; AB-5..8 | **G4: F1 + r* with CI** |
| 10 | **M8** replay + statistics | EX-5.1 replay; final bootstrap/Holm; figures | Replay within tolerance |
| 11 | **M9** report | EX-5.3 draft; crosscheck; ADR updates | Report contradicts nothing |
| 12 | **M10** release | Final PR; all issues closed; artifact bundle | **G5: merged with green CI** |

Every milestone lands as a PR with committed GPU manifests/metrics, passes the full CI gate set, resolves all linked issues, and carries an ADR for any watched-path change.

---

## 10. References

**High confidence** (anchors used directly in the design):

1. A. Gohr, "Improving Attacks on Round-Reduced Speck32/64 Using Deep Learning," CRYPTO 2019. — Neural distinguisher + key-ranking template; rank/AUC evaluation protocol. **High.**
2. A. Benamira, D. Gerault, T. Peyrin, Q. Q. Tan, "A Deeper Look at Machine Learning-Based Cryptanalysis," EUROCRYPT 2021. — Neural distinguishers largely approximate the differential distribution; motivates the log-DDT baseline, mixture features, and the expected null. **High.**
3. E. Biham, A. Shamir, *Differential Cryptanalysis of the Data Encryption Standard*, Springer 1993. — Last-round partial-decryption attack structure, characteristics, trail search. **High for method; exact data complexities medium** (to be recomputed by TH-1, not quoted from memory).
4. M. Matsui, "Linear Cryptanalysis Method for DES Cipher," EUROCRYPT 1993; "The First Experimental Cryptanalysis of DES," CRYPTO 1994. — Linear prior and KPA baseline; ~2^43 known-plaintext anchor for scoping R = 16. **High for method; exact figures medium.**
5. FIPS PUB 46-3, *Data Encryption Standard*. — Normative tables; source of KATs and the key-schedule coverage map. **High.**
6. E. Biham, "A Fast New DES Implementation in Software," FSE 1997. — Bitsliced implementation guidance. **High.**
7. M. Zaheer et al., "Deep Sets," NeurIPS 2017. — Permutation-invariant sum pooling as additive log-likelihood. **High.**
8. A. van den Oord, Y. Li, O. Vinyals, "Representation Learning with Contrastive Predictive Coding," 2018. — InfoNCE/listwise ranking loss. **High.**
9. S. Ross, G. Gordon, J. A. Bagnell, "A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning" (DAgger), AISTATS 2011. — Self-training on the search distribution (used only for the candidate-pool curriculum; the fatal beam-search version is rejected). **High.**
10. E. Jang, S. Gu, B. Poole, "Categorical Reparameterization with Gumbel-Softmax," ICLR 2017. — RelaxedCore ablation only. **High.**
11. G. Alain, Y. Bengio, "Understanding Intermediate Layers Using Linear Classifier Probes," arXiv:1610.01644, 2016; Y. Belinkov, "Probing Classifiers: Promises, Shortcomings, and Advances," Computational Linguistics 2022. — Probe methodology, capacity controls, shuffled-target nulls. **High.**
12. L. R. Knudsen, "Truncated and Higher Order Differentials," FSE 1994. — Truncated sets and masked match rates. **High.**
13. S. Langford, M. Hellman, "Differential-Linear Cryptanalysis," CRYPTO 1994. — Candidate stronger combined oracle if pure spectra die early. **High.**

**Medium confidence** (method sound; exact numbers to be verified/recomputed):

14. A. A. Selcuk, "On Probability of Success in Linear and Differential Cryptanalysis," J. Cryptology 2008. — Rank/success-vs-sample formulas supporting TH-3 and r*. **Medium.**
15. A. Jain, V. Kohli, G. Mishra, "Deep Learning-Based Cryptanalysis of Lightweight Block Ciphers," Security and Communication Networks 2020. — Protocol/data-budget comparison only. **Medium.**
16. Biham–Shamir per-round data complexities (4-, 6-, 8-round figures). — Treated as planning envelopes only; TH-1 recomputes them before any comparison table is written. **Medium.**

**Low confidence** (background only; must be verified before citation):

17. "Gohr, Leander, Neumann" — hypothesized work on assessing differential-neural distinguishers; title/venue unverified. **Low; do not cite until verified.**
18. "Baksi, Breier, Chen, Dong" — approximate title on ML-assisted differential distinguishers; exact citation unverified. **Low.**
19. Recent SoK/survey literature on deep-learning cryptanalysis. **Low; Phase-0 survey required before any novelty claim.**

---

*End of roadmap. The primary scientific risk is that the honest answer is "ML adds nothing measurable over the exact differential distribution on DES at feasible budgets." The plan is built so that this answer, if true, is produced rigorously, with pre-registered endpoints, calibrated controls, and defensible bounds — rather than discovered late and explained away.*