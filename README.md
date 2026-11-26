# ml-des-cryptanalysis

Neural cryptanalysis of round-reduced DES: reproducible known-plaintext
(KPA) and chosen-plaintext (CPA) experiments from 4 to 16 rounds.

> **Honest scope.** Sixteen rounds is full DES. On a single RTX 2060
> (6 GB) we do **not** expect to recover a 56-bit key at 16 rounds, and
> we do not expect to beat classical differential or linear attacks.
> The deliverable is a measured boundary: at which round count does the
> learned signal stop being useful, what did the network learn, and how
> does the cost compare with brute force and classical cryptanalysis.
> Negative results are first-class results here.

The previous stage of this research (a 16-bit SPN toy, a differentiable
cipher decomposition, and a candidate-key refinement network that
reached ~27% recovery at 2 rounds and failed at 4) is archived at
[`research/background/original-readme.md`](research/background/original-readme.md).

## Status

**Stage 0 complete; 6-round CPA key recovery achieved.** A 5-round
full-active differential trail, a key-independent right-pair filter, and
a characteristic-match last-round test recover a 56-bit DES key at six
rounds from 323M chosen pairs (4 right pairs, fixed top-2 protocol,
48,896 schedule candidates, verified by re-encryption). This is a
single-target-key demonstration with large data complexity, not a
practical break of DES, and the 6-round key ranking is classical rather
than neural. The 2-round SPADE chunk scorer
reaches 0.39 chunk accuracy versus the DDT's 0.0; the 6-round neural
scorer remains a negative scaling result. The repository contains:

- a bit-exact reference DES with round-reduced variants
  ([`src/des_ml/des.py`](src/des_ml/des.py));
- a vectorised PyTorch DES for GPU data generation and verification
  ([`src/des_ml/des_torch.py`](src/des_ml/des_torch.py));
- key-disjoint KPA/CPA data streams with a deterministic 80/10/10 split
  ([`src/des_ml/data.py`](src/des_ml/data.py));
- a residual CNN distinguisher and an MLP baseline
  ([`src/des_ml/models/pair_cnn.py`](src/des_ml/models/pair_cnn.py));
- exact DDT/LAT tables, key-schedule coverage and last-round chunk algebra
  ([`src/des_ml/theory/`](src/des_ml/theory), [`src/des_ml/last_round.py`](src/des_ml/last_round.py));
- a training entry point that writes CI-verifiable result manifests
  ([`src/des_ml/train/train_distinguisher.py`](src/des_ml/train/train_distinguisher.py));
- seven blocking CI gates plus a non-blocking LLM review agent
  ([`AGENTS.md`](AGENTS.md), [`.github/workflows/`](.github/workflows)).

No scientific claim is made yet. The first experiment is Stage 1.

## Quick start

```bash
# CPU-only smoke run (also used by CI)
python -m venv .venv && . .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e '.[dev]'

pytest -q
python scripts/run_conformance.py
python -m des_ml.train.train_distinguisher \
  --config configs/smoke.yaml --max-steps 3 --device cpu --no-checkpoint
```

Real experiments run on the GPU host, not on the controller or in CI:

```bash
bash scripts/remote/sync.sh          # push the current commit as a bundle
bash scripts/remote/run.sh exp/des4  # detached training on D:\research\ml-des
bash scripts/remote/fetch.sh         # pull results/<stage>/<run_id>/
```

See [`scripts/remote/README.md`](scripts/remote/README.md) and
[ADR-0004](docs/adr/0004-remote-execution.md).

## Research design

Key recovery is **not** posed as regression over the 56-bit key. The
last round of DES factors into eight independent 64-way subkey
hypotheses, and the key schedule is GF(2)-linear, so recovering the
48-bit round key leaves only `2^8 = 256` master-key completions to
verify. The chosen base arm is **SPADE** — S-box-factorised last-round
scoring with a DDT-initialised residual, sum-pooled log-likelihood
aggregation, exact schedule decoding, and re-encryption verification.
See [ADR-0008](docs/adr/0008-research-strategy-spade.md) and
[`docs/ROADMAP.md`](docs/ROADMAP.md).

| Rounds | CPA expectation | KPA expectation | Claim class |
|---|---|---|---|
| 4 | Full-key recovery near-certain at modest data; matched against classical differential | High via linear/parity prior | Demonstrated result |
| 6 | High; the scientific question is the comparison with classical | Moderate | Demonstrated result / boundary |
| 8 | **Primary endpoint F1**; full-key versus classical likely negative | Chance-to-weak | Confirmatory test |
| 10 | Chunk AUC possibly marginal; full key ~0 | Chance | Boundary measurement |
| 12–16 | Null expected | Null expected | Negative result / certificate |

Pre-registered falsifiers F1–F6 are frozen in
[ADR-0006](docs/adr/0006-pre-registered-endpoints.md). The register is
[`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md). The plain `PairCNN`
configs under [`configs/distinguisher/`](configs/distinguisher) are
baselines and smoke tests, not the SPADE plan.

## Governance

Research is managed as a project: issues carry hypotheses, branches are
short-lived, `main` only accepts pull requests merged with a merge commit
(provenance audited), and every code-changing PR must ship a run manifest
produced on the GPU host.

- Rules for humans and agents: [`AGENTS.md`](AGENTS.md)
- Decisions: [`docs/adr/`](docs/adr)
- CI gates: [`.github/workflows/`](.github/workflows)
- Review agent: [`docs/REVIEW-AGENT.md`](docs/REVIEW-AGENT.md)
- Ship checklist: [`docs/SHIP-CHECKLIST.md`](docs/SHIP-CHECKLIST.md)

Required checks: `ci`, `adr-guard`, `adr-numbers`, `link-check`,
`release-blockers`, `results-gate`, `issue-gate`. The LLM review agent
is deliberately **not** a required check: it comments and files issues,
but never holds a veto.

## Hardware

- Training: Windows 11, RTX 2060 (6 GB), i7-10750H, 16 GB RAM, no WSL.
- Orchestration/CI: Linux controller, 2 GB RAM; GitHub Actions runners
  for CPU smoke tests only.

## References

- Gohr, *Improving Attacks on Round-Reduced Speck32/64 Using Deep
  Learning*, CRYPTO 2019.
- Benamira, Gerault, Peyrin, Tan, *A Deeper Look at Machine
  Learning-Based Cryptanalysis*, EUROCRYPT 2021.

Citations are kept in [`docs/ROADMAP.md`](docs/ROADMAP.md) with
confidence labels; verify before quoting.

## License

Not chosen yet. Treat the repository as private until an explicit
license is added.
