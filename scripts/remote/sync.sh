#!/usr/bin/env bash
# Push the current commit to the GPU host as a git bundle and check it out.
set -euo pipefail

: "${DES_SSH_HOST:=192.168.137.1}"
: "${DES_SSH_USER:=user}"
: "${DES_SSH_KEY:=$HOME/.ssh/des_remote}"
: "${DES_REMOTE_ROOT:=D:/research/ml-des}"

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"
BRANCH=${1:-$(git rev-parse --abbrev-ref HEAD)}
SHA=$(git rev-parse HEAD)

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "bundling $BRANCH @ $SHA"
git bundle create "$TMP/repo.bundle" --all >/dev/null

scp -q -i "$DES_SSH_KEY" \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$TMP/repo.bundle" "$DES_SSH_USER@$DES_SSH_HOST:$DES_REMOTE_ROOT/repo.bundle"
scp -q -i "$DES_SSH_KEY" \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$REPO_ROOT/scripts/remote/sync.ps1" "$DES_SSH_USER@$DES_SSH_HOST:$DES_REMOTE_ROOT/sync.ps1"
scp -q -i "$DES_SSH_KEY" \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$REPO_ROOT/scripts/remote/run_experiment.ps1" "$DES_SSH_USER@$DES_SSH_HOST:$DES_REMOTE_ROOT/run_experiment.ps1"

ssh -i "$DES_SSH_KEY" \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "$DES_SSH_USER@$DES_SSH_HOST" \
  "powershell.exe -NoProfile -ExecutionPolicy Bypass -File $DES_REMOTE_ROOT\\sync.ps1 -Branch $BRANCH -Sha $SHA"
