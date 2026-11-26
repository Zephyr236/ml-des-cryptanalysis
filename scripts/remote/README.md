# Remote GPU execution

The controller machine has no GPU and 2 GB of RAM. Real training runs
on a Windows 11 host with an RTX 2060 (6 GB).

## Addresses and paths

| Item | Value |
|---|---|
| Host | `192.168.137.1` |
| User | `user` |
| Remote root | `D:\research\ml-des` |
| Repo checkout | `D:\research\ml-des\repo` |
| Python | `D:\research\ml-des\.venv\Scripts\python.exe` |
| Logs | `D:\research\ml-des\logs\` |

Authentication is an SSH key, by default `~/.ssh/des_remote`. **No
password is stored in this repository.** Override the defaults with:

```bash
export DES_SSH_HOST=192.168.137.1
export DES_SSH_USER=user
export DES_SSH_KEY=$HOME/.ssh/des_remote
export DES_REMOTE_ROOT='D:\research\ml-des'
```

## Bootstrap (once)

```bash
scripts/remote/psrun.sh scripts/remote/bootstrap.ps1
```

Installs `uv`, CPython 3.12 and PyTorch CUDA 12.4 into the remote root.
It is idempotent: an existing `.venv` is reused.

## Sync a commit

```bash
scripts/remote/sync.sh            # current branch and HEAD
scripts/remote/sync.sh main       # a specific branch
```

The script creates a git bundle, copies it to the host, fetches it into
`D:\research\ml-des\repo`, checks out the branch and verifies that the
remote HEAD equals the local commit.

## Run an experiment

```bash
scripts/remote/run.sh configs/distinguisher/des4-kpa.yaml results/stage1
```

This syncs first, then starts a detached SSH session that runs the
training script on CUDA. The local log is `logs/remote-<timestamp>.log`.
Because the launcher runs under `nohup`, closing the terminal does not
kill the remote process, but the controller must stay up to keep the
SSH channel.

When the manifest appears, fetch it:

```bash
scripts/remote/fetch.sh results/stage1/<run_id>
```

## Notes

- The remote host never receives a GitHub token. Code arrives as a
  bundle; results leave over `scp`.
- `DES_CODE_SHA` is set from the local commit before training, so the
  manifest points at a revision that exists in the PR.
- If SSH is interrupted, the run continues; re-run `fetch.sh` later.
- Windows quoting is handled by passing PowerShell scripts as files
  (`psrun.sh` base64-encodes them) rather than inline commands.
