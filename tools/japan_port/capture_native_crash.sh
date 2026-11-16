#!/usr/bin/env bash
# Collect a real native stack trace for Japanese gameplay crashes.
# Requires: sudo apt install gdb
# Run from any directory: bash tools/japan_port/capture_native_crash.sh
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
binary="${GOEMON_JP_BINARY:-$repo_root/Goemon64RecompiledJP}"
log="${GOEMON_JP_CRASH_LOG:-$HOME/goemon-japan-crash.log}"

if ! command -v gdb >/dev/null 2>&1; then
    printf 'gdb missing. On Ubuntu install with: sudo apt install gdb\n' >&2
    exit 2
fi
if [[ ! -x "$binary" ]]; then
    printf 'Japanese native executable not found: %s\n' "$binary" >&2
    exit 2
fi
if [[ ! -f "$repo_root/assets/launcher-jp.rml" ]]; then
    printf 'Japanese launcher assets not found in %s\n' "$repo_root" >&2
    exit 2
fi

printf 'Starting Japanese game under gdb. Play until the crash occurs.\n'
printf 'Crash report will be saved to: %s\n' "$log"
# The native loader expects paths relative to repository root. Capture both
# game logging and GDB frames in one report, even when the process segfaults.
cd "$repo_root"
gdb -q --batch \
    -ex 'set pagination off' \
    -ex 'set print thread-events off' \
    -ex 'set confirm off' \
    -ex 'handle SIGPIPE nostop noprint pass' \
    -ex 'run' \
    -ex 'printf "\n=== CRASHING THREAD ===\n"' \
    -ex 'bt 30' \
    -ex 'printf "\n=== ALL THREADS ===\n"' \
    -ex 'thread apply all bt 12' \
    -ex 'printf "\n=== REGISTERS ===\n"' \
    -ex 'info registers' \
    --args "$binary" "$@" > "$log" 2>&1 || true

printf '\nSaved report: %s\n' "$log"
printf 'Last 85 lines:\n'
tail -n 85 "$log"
