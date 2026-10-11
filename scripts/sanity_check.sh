#!/usr/bin/env bash
# Quick sanity pipeline used before handing the project to a reviewer:
# installs checks, doctor, fast test subset, one verify slice.
set -uo pipefail
cd "$(dirname "$0")/.."

if [ -z "${COMPREG_BIN:-}" ]; then
    if [ -x ".venv/bin/compreg" ]; then COMPREG_BIN=".venv/bin/compreg"; else COMPREG_BIN="$(command -v compreg)"; fi
fi
PY="$(dirname "$COMPREG_BIN")/python3"; [ -x "$PY" ] || PY="python3"

echo "== pytest (not slow):"
"$PY" -m pytest -m "not slow" 2>&1 | tail -2

echo "== compreg doctor:"
"$COMPREG_BIN" doctor 2>&1 | grep -E "compiler|sqlite|corpus integrity"

echo "== verify (O2 subset):"
"$COMPREG_BIN" verify --opts O2 --tests arithmetic_int_basic sorting_bubble_sort \
  structs_point_distance loops_collatz_lengths bench_int_workload 2>/dev/null | grep -E "^total="

echo "== ctest:"
"$COMPREG_BIN" ctest 2>&1 | tail -3
