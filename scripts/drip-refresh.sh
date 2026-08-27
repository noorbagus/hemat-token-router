#!/usr/bin/env bash
# Refresh DRIP file baselines.
#
# DRIP substitutes `Read` results with `[DRIP: ...]` headers; a 0-byte
# "unchanged since last read" means the baseline was set by another
# session/subagent. Recovery is exactly ONE `drip refresh` call per file.
#
# Reference: DEVELOPMENT.md and arsitektur/arsitektur-v2.0-sdlc.md §13.1.

set -euo pipefail

if ! command -v drip >/dev/null 2>&1; then
  echo "scripts/drip-refresh.sh: 'drip' not on PATH; nothing to refresh (no-op)" >&2
  exit 0
fi

if [[ $# -eq 0 ]]; then
  echo "Usage: scripts/drip-refresh.sh <path> [path...]" >&2
  echo "Refresh DRIP baseline for one or more files (one 'drip refresh' call per file)." >&2
  exit 2
fi

for path in "$@"; do
  drip refresh "$path"
done
