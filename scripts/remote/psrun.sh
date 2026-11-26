#!/usr/bin/env bash
# Run a local PowerShell script on the GPU host.
#
#   scripts/remote/psrun.sh path/to/script.ps1
#
# The script is base64-encoded as UTF-16LE and passed via
# -EncodedCommand, which avoids Windows quoting problems.
set -euo pipefail

: "${DES_SSH_HOST:=192.168.137.1}"
: "${DES_SSH_USER:=user}"
: "${DES_SSH_KEY:=$HOME/.ssh/des_remote}"

script="${1:?usage: psrun.sh <script.ps1>}"
encoded=$(python3 - "$script" <<'PY'
import base64
import sys

with open(sys.argv[1], "rb") as handle:
    payload = handle.read().decode("utf-8")
print(base64.b64encode(payload.encode("utf-16le")).decode("ascii"))
PY
)

exec ssh -i "$DES_SSH_KEY" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ConnectTimeout=15 \
  -o ServerAliveInterval=30 \
  "$DES_SSH_USER@$DES_SSH_HOST" \
  "powershell.exe -NoProfile -EncodedCommand $encoded"
