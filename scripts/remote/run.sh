#!/usr/bin/env bash
# Sync the current commit and start a training run on the GPU host.
#
#   scripts/remote/run.sh configs/distinguisher/des4-kpa.yaml results/stage1 [max_steps]
#
# The SSH process is detached with nohup; its local log is printed.
set -euo pipefail

: "${DES_SSH_HOST:=192.168.137.1}"
: "${DES_SSH_USER:=user}"
: "${DES_SSH_KEY:=$HOME/.ssh/des_remote}"
: "${DES_REMOTE_ROOT:=D:/research/ml-des}"

CONFIG=${1:?usage: run.sh <config> [out] [max_steps]}
OUT=${2:-results/stage1}
MAX_STEPS=${3:-0}

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"
bash "$REPO_ROOT/scripts/remote/sync.sh"

SHA=$(git rev-parse HEAD)
mkdir -p "$REPO_ROOT/logs"
STAMP=$(date +%Y%m%dT%H%M%S)
LOG="$REPO_ROOT/logs/remote-$STAMP.log"

nohup ssh -i "$DES_SSH_KEY" \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=1000 \
  "$DES_SSH_USER@$DES_SSH_HOST" \
  "powershell.exe -NoProfile -ExecutionPolicy Bypass -File $DES_REMOTE_ROOT\\run_experiment.ps1 -Config $CONFIG -Out $OUT -CodeSha $SHA -MaxSteps $MAX_STEPS" \
  >"$LOG" 2>&1 &

echo $! > "$LOG.pid"
echo "started pid $(cat "$LOG.pid")"
echo "log: $LOG"
echo "fetch with: scripts/remote/fetch.sh <run_dir>"
