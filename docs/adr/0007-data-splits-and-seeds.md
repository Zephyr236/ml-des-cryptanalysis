# 0007. Data splits, hashing and seeds

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Zephyr236, Claude Code

## Context

DES has a 56-bit effective key. A split by sample rather than by key
lets the same key appear in train and test, which is the most plausible
explanation for optimistic results in the previous 16-bit prototype.
The split must be deterministic, reproducible without our RNG state,
and cheap enough to evaluate inside a GPU data stream.

The roadmap specifies `SHA-256(master_key ‖ salt)`. A per-key SHA-256
in Python cannot keep up with GPU-side rejection sampling at millions
of keys per run; the split must be a vectorised integer hash.

## Decision

1. **Unit of splitting is the 56-bit effective key**, `PC1(key)`.
   Parity-bit variants therefore map to the same bucket.
2. **Hash.** `bucket = SplitMix64_finalizer(effective_key XOR SALT) mod
   100`, with `SALT = 0x5EED5EED5EED5E`. The finalizer uses 64-bit
   wrapping multiply and **logical** right shifts:
   ```
   h = key ^ SALT
   h ^= h >> 30;  h *= 0xBF58476D1CE4E5B9
   h ^= h >> 27;  h *= 0x94D049BB133111EB
   h ^= h >> 31
   bucket = (h & 0x7FFF_FFFF_FFFF_FFFF) % 100
   ```
   SHA-256 remains the reference definition for external
   re-implementations; the SplitMix64 construction is a performance
   substitution that must produce the same *properties* (determinism,
   parity invariance, 80/10/10 balance), not the same buckets.
3. **Buckets.** `0..79` train, `80..89` validation, `90..99` test.
   The split version string `splitmix64-v1` is recorded in run tags and
   manifests.
4. **Rejection sampling.** A stream emits a key only if its bucket
   matches; otherwise it resamples. Training therefore uses the 80% of
   keys in bucket 0 and never sees validation or test keys.
5. **Additional holdout.** A contiguous range of the effective-key
   space is reserved as an extrapolation stress test; it is reported
   separately and is not part of the main 80/10/10 split.
6. **Weak keys.** The four DES weak keys and six semi-weak keys are
   excluded from headline splits and reported separately if encountered.
7. **Seeds.** Seeds 0–4 for `R ≤ 8`; seeds 0–2 for `R ≥ 10`. All seeds
   are fixed before runs. Every run is registered, including failures
   and wall-clock-censored runs.
8. **RNG streams.** Keys, plaintexts and negatives are drawn from
   independent GPU-side generator streams whose seeds are recorded in
   the manifest. `num_workers = 0` until a host-RAM smoke test proves
   otherwise.

## Consequences

- Rejection sampling costs roughly 1/0.8 in training throughput; this
  is accepted.
- Changing `SALT` or the finalizer invalidates every split and requires
  a new ADR plus a full rerun; the version string makes this visible.
- The CI split test verifies determinism, parity invariance and balance
  (80/10/10 within Monte-Carlo error) on a large sample.
- External readers can reproduce the split from `src/des_ml/data.py`
  without knowing our seeds.

## Alternatives considered

- **SHA-256 per key on the GPU.** Correct but too slow in pure Python;
  a CUDA implementation would add a dependency and a second code path.
- **Split by key index modulo 100.** Not key-derived; parity variants
  and structured key families leak across splits.
- **Random split per run.** Not reproducible and invites accidental
  test-set reuse.
