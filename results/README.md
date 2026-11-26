# Results

Every directory here is produced by a committed script and carries a
`manifest.json` that ties it to a git revision, a config hash, a seed
and the environment that produced it.

```
results/
  LATEST.json                  pointer to the most recently accepted run
  stage0/des-conformance-.../  DES correctness evidence
  stage1/des4-kpa-.../         distinguisher runs
  stage2/...                   key-recovery runs
```

Rules:

- Do not hand-edit a manifest. Regenerate the run.
- Failed runs stay in the repository with `status: failed`.
- Weight files (`*.pt`) are ignored by git; put a hash and a path in the
  manifest instead.
- `results/LATEST.json` must be updated by the same PR that adds the run.

Schema and helpers: [`src/des_ml/manifest.py`](../src/des_ml/manifest.py).
Protocol: [ADR-0002](../docs/adr/0002-experiment-protocol.md).
