@AGENTS.md

# Claude Code notes

- The canonical rules are in `AGENTS.md`; this file only imports them.
- Never push to `main`. Work on a branch and open a PR.
- Every code/config PR needs a result manifest under `results/` whose
  `code_sha` is a commit in the PR, plus a fresh `results/LATEST.json`.
- Run experiments on the GPU host described in `scripts/remote/README.md`;
  this controller has 2 GB of RAM and no GPU.
- Treat the review agent's issues as advisory but respond to every
  high/medium finding in the PR thread.
