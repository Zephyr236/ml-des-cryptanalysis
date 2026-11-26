#!/usr/bin/env bash
# Pull a result directory back from the GPU host.
#
#   scripts/remote/fetch.sh results/stage1/<run_id>
set -euo pipefail

: "${DES_SSH_HOST:=192.168.137.1}"
: "${DES_SSH_USER:=user}"
: "${DES_SSH_KEY:=$HOME/.ssh/des_remote}"
: "${DES_REMOTE_ROOT:=D:/research/ml-des}"

RUN_REL=${1:?usage: fetch.sh results/<stage>/<run_id>}
RUN_REL=${RUN_REL#results/}
REPO_ROOT=$(git rev-parse --show-toplevel)
DEST="$REPO_ROOT/results/$(dirname "$RUN_REL")"
mkdir -p "$DEST"

scp -r -q -i "$DES_SSH_KEY" \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$DES_SSH_USER@$DES_SSH_HOST:$DES_REMOTE_ROOT/repo/results/$RUN_REL" "$DEST/"

echo "fetched $RUN_REL -> $DEST/"
