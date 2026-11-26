# 0002. Experiment protocol and result manifests

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Zephyr236, Claude Code

## Context

Machine-learning cryptanalysis has a specific failure mode: a model can
appear to recover a key because it memorised the key, because the test
set overlapped the training set, or because the "success" criterion was
weaker than key recovery. The previous 16-bit SPN result (~27% at 2
rounds) had no key-disjoint split and no budget-matched baseline, so it
cannot distinguish learning from memorisation.

DES has a 56-bit effective key. Any claim at 4–16 rounds will be read
against classical differential and linear attacks, so the protocol must
report the same quantities those attacks report: data complexity, time
complexity, success probability, and the number of trials.

## Decision

1. **Split by key, not by sample.** Keys are hashed from their 56-bit
   effective form into 80/10/10 train/val/test buckets. A stream only
   emits keys from its bucket. Parity-bit variants hash to the same
   bucket.
2. **Target key never enters the model.** Candidate keys may enter a
   scorer only as the attacker's own state; the target `K*` is used for
   labels and verification only.
3. **Every experiment carries four baselines:** budget-matched random
   search, brute force cost, the best classical differential/linear
   distinguisher at the same round count, and shuffled-label plus
   random-permutation controls.
4. **Statistics:** at least three seeds; report mean, standard
   deviation and a 95% interval (Wilson for proportions, bootstrap for
   AUC). Fourteen round × setting combinations are exploratory unless a
   correction is stated.
5. **Verification by the real cipher.** A success is only counted when
   re-encryption with the recovered key reproduces every held-out
   plaintext/ciphertext pair.
6. **Compute accounting:** report training cost in DES-encryption
   equivalents (`batch × steps × pairs_per_key`) and compare with `2^56`
   as an order-of-magnitude statement, not a hardware benchmark.
7. **Manifests are mandatory.** Every run writes `manifest.json` via
   `des_ml.manifest.RunWriter`, including failed runs. The results gate
   rejects manifests whose `code_sha` is not in the PR or whose working
   tree was dirty.
8. **Negative results are recorded, not deleted.** A high-round failure
   must include a diagnostic that separates "representation cannot
   learn" from "decoder cannot use the signal" (e.g. rank of the true
   key among all candidates).

## Consequences

- Data generation must reject and resample keys outside the requested
  bucket; this costs some throughput (roughly 1/0.8 for training).
- The val/test keys are fixed by a public hash, so another researcher
  can reproduce the split without our seed.
- Committing manifests and logs grows the repository. Weight files are
  ignored; large artefacts must be linked instead.
- A failed run still adds a directory, which is the point.

## Alternatives considered

- **Split by key index modulo N.** Rejected: DES key equivalence means
  parity variants would leak across splits.
- **Random split per run.** Rejected: not reproducible without the RNG
  state.
- **Store only aggregate metrics in the manifest.** Rejected: the JSONL
  trace is what lets a reviewer see that a "converged" run was actually
  a lucky seed.
