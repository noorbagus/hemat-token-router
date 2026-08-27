#!/usr/bin/env bash
# csmart verification driver.
#
# Runs the project's test/typecheck/smoke gates with the RTK-safe interpreter.
# Bare `pytest` resolves to a broken Python 3.9 (ModuleNotFoundError: urllib3);
# python3.14 is the project interpreter with all deps. pyright is a standalone
# binary, NOT a Python 3.14 module.
#
# Reference: DEVELOPMENT.md and arsitektur/arsitektur-v2.0-sdlc.md §13.1.

set -euo pipefail
cd "$(dirname "$0")/.."

RTK_OK=0
if command -v rtk >/dev/null 2>&1; then
  RTK_OK=1
  RTK_PREFIX=(rtk proxy python3.14 -m pytest)
else
  RTK_PREFIX=(python3.14 -m pytest)
fi

usage() {
  cat >&2 <<'EOF'
Usage: scripts/verify.sh <subcommand> [args...]

Subcommands:
  test        Run pytest (RTK-safe interpreter); forwards extra args
  typecheck   Run pyright on router/ csmart.py (standalone binary)
  smoke       Run csmart --dry-run --json (no Claude dispatch)
  all         Run test, then typecheck, then smoke (non-zero on any failure)

Examples:
  scripts/verify.sh test tests/test_cli.py -q
  scripts/verify.sh all
EOF
  exit 2
}

cmd_test() {
  "${RTK_PREFIX[@]}" "$@"
}

cmd_typecheck() {
  pyright router/ csmart.py
}

cmd_smoke() {
  if (( RTK_OK )); then
    rtk proxy python3.14 -m csmart --dry-run --json "smoke: list router modules" >/dev/null
  else
    python3.14 -m csmart --dry-run --json "smoke: list router modules" >/dev/null
  fi
}

cmd_all() {
  cmd_test
  cmd_typecheck
  cmd_smoke
}

subcmd="${1:-}"
if [[ -z "$subcmd" ]]; then
  usage
fi
shift

case "$subcmd" in
  test)      cmd_test "$@" ;;
  typecheck) cmd_typecheck ;;
  smoke)     cmd_smoke ;;
  all)       cmd_all ;;
  *)         usage ;;
esac
