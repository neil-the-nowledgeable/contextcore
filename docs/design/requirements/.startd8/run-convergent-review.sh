#!/usr/bin/env bash
# Run convergent review: plan against requirements
# Config: convergent-review-2026-02-19T1855Z.json
# Created: 2026-02-19T18:55Z

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${1:-$SCRIPT_DIR/convergent-review-2026-02-19T1855Z.json}"
SDK_DIR="$HOME/Documents/dev/startd8-sdk"

if [ ! -f "$CONFIG" ]; then
  echo "ERROR: Config not found: $CONFIG" >&2
  exit 1
fi

cd "$SDK_DIR"
exec startd8 workflow run convergent-review --config "$CONFIG"
