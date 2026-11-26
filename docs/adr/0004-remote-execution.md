# 0004. Remote GPU execution topology

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Zephyr236, Claude Code

## Context

The controller machine has 2 GB of RAM and no GPU. Training runs on a
Windows 11 laptop at `192.168.137.1` with an RTX 2060 (6 GB), an
i7-10750H and 16 GB of RAM; WSL is not installed. GitHub-hosted runners
are CPU-only and cannot reach a private LAN address. The repository is
private.

We need a way for an agent to: sync an exact commit, launch a long
training run that survives an SSH disconnect, monitor it, and pull back
a result directory that the results gate can verify.

## Decision

1. **The GPU host is the only training environment.** CI runs a
   three-step CPU smoke test; it never runs a real experiment.
2. **Authentication is by SSH key.** The controller holds
   `~/.ssh/des_remote`; the public key is installed in the host's
   `administrators_authorized_keys`. The password used during bootstrap
   is not stored in the repository or in any script.
3. **Python is provisioned with `uv`** under
   `D:\research\ml-des\.venv` (CPython 3.12, PyTorch CUDA 12.4). The
   virtualenv is disposable and rebuilt from `pyproject.toml`.
4. **Code is synced as a git bundle or an archive**, never by cloning a
   private repository with a personal token on the Windows host. The
   controller records the commit and passes `DES_CODE_SHA` to the run so
   the manifest points at real history.
5. **Runs are detached.** The launcher starts a PowerShell process with
   its own log file under `D:\research\ml-des\logs\`; the SSH session
   may close. The controller polls the log and the manifest.
6. **Results are pulled back with `scp`**, then committed on a branch.
   Large checkpoints stay on the host and are linked by path and hash.
7. **No credentials on the host.** The host may hold the SSH public key
   for the controller only. GitHub tokens, Anthropic keys and SSH
   private keys stay on the controller or in GitHub Actions secrets.

## Consequences

- There is no push-to-run automation from GitHub to the LAN host. This
  is a deliberate trade: a self-hosted runner on a public repository
  would execute fork code on the researcher's laptop.
- The controller must stay reachable to the host during a run's launch
  and fetch, but not during training.
- Windows quoting is awkward. PowerShell scripts are passed as
  base64-encoded commands or copied as files; the repository contains
  small wrappers under `scripts/remote/`.
- Reproducibility depends on `DES_CODE_SHA` being set correctly. The
  results gate catches the case where it is not a commit in the PR.

## Alternatives considered

- **Self-hosted GitHub Actions runner on the Windows host.** Rejected
  for a private repo only with hesitation: it couples the laptop to
  GitHub availability, and a workflow change could execute arbitrary
  code on it. The bundle/scp path is simpler and auditable.
- **WSL on the host.** Not installed; installation needs admin and a
  reboot, and the 6 GB GPU is already usable from native Windows
  PyTorch.
- **Cloud GPU.** Cost and data-upload friction; the local 2060 is
  adequate for the planned model sizes.
