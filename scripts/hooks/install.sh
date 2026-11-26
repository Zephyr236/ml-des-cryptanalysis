#!/usr/bin/env bash
# Install the repository hooks into .git/hooks.
set -euo pipefail
ROOT=$(git rev-parse --show-toplevel)
ln -sf ../../scripts/hooks/pre-commit "$ROOT/.git/hooks/pre-commit"
chmod +x "$ROOT/scripts/hooks/pre-commit"
echo "installed pre-commit hook"
