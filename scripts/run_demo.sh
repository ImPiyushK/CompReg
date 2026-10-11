#!/usr/bin/env bash
# CompReg demonstration scenarios (documented, repeatable, honest).
#
# Usage: scripts/run_demo.sh [scenario-number|all]
# Scenarios:
#   1successful verification across configs
#   2controlled correctness regression detection
#   3compilation-failure and timeout classification
#   4regression statistics with synthetic injected measurements (algorithm validation)
#   5historical baseline flow + real wall-clock performance regression
#   6triage artifact + minimization preserving the failure
#   7ctest + pytest through the automation entry points
#
# Requirements: python >= 3.11 with `compreg` installed (pip install -e ".[dev]")
# and at least one of gcc/clang. Missing optional compilers are reported
# transparently by the tool.

set -uo pipefail

DEMO_DIR="${DEMO_DIR:-artifacts/demo}"
mkdir -p "$DEMO_DIR"

# Resolve the compreg entry point: explicit env override -> local .venv -> PATH.
if [ -n "${COMPREG_BIN:-}" ]; then
    :
elif [ -x ".venv/bin/compreg" ]; then
    COMPREG_BIN=".venv/bin/compreg"
else
    COMPREG_BIN="$(command -v compreg || true)"
fi
if [ -z "${COMPREG_BIN:-}" ]; then
    echo "error: compreg not found; install with 'pip install -e .[dev]' or set COMPREG_BIN" >&2
    exit 3
fi
# Matching interpreter (venv sibling of compreg when applicable).
PY="${PY:-$(dirname "$COMPREG_BIN")/python3}"
[ -x "$PY" ] || PY="python3"
ctest() { "$PY" -m pytest "$@"; }


note() { printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }

scenario_1() {
    note "Scenario 1: successful verification across compiler configurations"
    "$COMPREG_BIN" verify --opts O0,O2,O3 | tee "$DEMO_DIR/verify_summary.txt"
    echo "exit=$?" | tee -a "$DEMO_DIR/verify_summary.txt"
}

scenario_2() {
    note "Scenario 2: controlled correctness regression (inverted comparison)"
    expected_path="test_corpus/sorting/sorting_bubble_sort.expected"
    set +e
    "$COMPREG_BIN" verify --opts O2 \
      --ad-hoc-source examples/broken_bubble_sort.cpp \
      --ad-hoc-expected "$expected_path" \
      | tee "$DEMO_DIR/mismatch_demo.txt"
    rc=$?
    set -e
    echo "exit=$rc (1 = verification failure detected)" | tee -a "$DEMO_DIR/mismatch_demo.txt"
}

scenario_3() {
    note "Scenario 3: compile-error and timeout classification"
    set +e
    "$COMPREG_BIN" verify --opts O2 --ad-hoc-source examples/compile_error.cpp --no-db \
      | tee "$DEMO_DIR/compile_fail_demo.txt"
    echo "exit=$?" | tee -a "$DEMO_DIR/compile_fail_demo.txt"

    "$COMPREG_BIN" verify --opts O2 --timeout 2 --ad-hoc-source examples/infinite_loop.cpp --no-db \
      | tee "$DEMO_DIR/timeout_demo.txt"
    echo "exit=$?" | tee -a "$DEMO_DIR/timeout_demo.txt"
    set -e
    note "failed compile must not proceed to execution:"
    grep -q "attempted" "$DEMO_DIR/compile_fail_demo.txt" || \
      echo "execution_result is absent for COMPILE_ERROR outcomes (asserted by integration tests)" \
      | tee -a "$DEMO_DIR/compile_fail_demo.txt"
}

scenario_4() {
    note "Scenario 4: regression detection ALGORITHM with synthetic measurements"
    "$PY" - <<'EOF' | tee "$DEMO_DIR/synthetic_stats_demo.txt"
"""Deterministic validation of the statistical regression rule.

No wall-clock claims are made here; this proves the detection algorithm."""
import random
from compreg.benchmarking.regression import RegressionPolicy, evaluate_regression
from compreg.benchmarking.statistics import compute_stats

random.seed(8675309)
policy = RegressionPolicy(min_samples=5, rel_threshold=0.20, abs_threshold_s=0.010, noise_k_mad=3.0)

# Case A: baseline noise (jitter within ±ms), current run slightly slower.
base = compute_stats([0.100 + random.uniform(-0.002, 0.002) for _ in range(9)])
same = compute_stats([0.101 + random.uniform(-0.002, 0.002) for _ in range(9)])
print("baseline median        :", round(base.median_s, 5), "MAD", round(base.mad_s, 5))
print("+1% jitter verdict     :", evaluate_regression(
    policy=policy, test_id="demo", config_hash="c",
    baseline=base, current=same).verdict)

# Case B: noisy current run that stays INSIDE the noise floor.
noisy = compute_stats([0.115 + random.uniform(-0.004, 0.004) for _ in range(9)])
print("+15% but inside 3*Mad  :", evaluate_regression(
    policy=policy, test_id="demo", config_hash="c",
    baseline=base, current=noisy).verdict)

# Case C: a real regression (median +60% >> noise floor).
slow = compute_stats([0.160 + random.uniform(-0.002, 0.002) for _ in range(9)])
verdict = evaluate_regression(policy=policy, test_id="demo", config_hash="c",
                              baseline=base, current=slow)
print("+60% clear regression  :", verdict.verdict,
      f"({verdict.slowdown_pct:.1f}%)")

# Case D: too few samples - refused, never a false positive.
few = compute_stats([0.16, 0.17, 0.15])
print("3 samples only         :", evaluate_regression(
    policy=policy, test_id="demo", config_hash="c",
    baseline=base, current=few).verdict)
EOF
}

scenario_5() {
    note "Scenario 5: historical baseline flow + REAL wall-clock regression"
    expected="test_corpus/benches/bench_int_workload.expected"

    "$COMPREG_BIN" benchmark --opts O2 --reps 5 --warmup 1 --tests demo_workload \
      --ad-hoc-bench test_corpus/benches/bench_int_workload.cpp \
      --ad-hoc-id demo_workload --ad-hoc-expected "$expected" \
      | tee "$DEMO_DIR/bench_fast.txt"
    "$COMPREG_BIN" baseline create | tee "$DEMO_DIR/baseline_create.txt"

    set +e
    presl=$("$COMPREG_BIN" history --limit 1 2>/dev/null | awk 'NR==3{print $1}')
    set -e
    echo "baseline source run: $presl"

    "$COMPREG_BIN" benchmark --opts O2 --reps 5 --warmup 1 --tests demo_workload \
      --ad-hoc-bench examples/slow_int_workload.cpp \
      --ad-hoc-id demo_workload --ad-hoc-expected "$expected" \
      | tee "$DEMO_DIR/bench_slow.txt"
    sl=$("$COMPREG_BIN" history --limit 1 2>/dev/null | awk 'NR==3{print $1}')

    set +e
    "$COMPREG_BIN" compare --run "$sl" --baseline "$presl" | tee "$DEMO_DIR/regression_compare.txt"
    rc=$?
    set -e
    echo "compare exit=$rc (1 = regression detected)" | tee -a "$DEMO_DIR/regression_compare.txt"
}

scenario_6() {
    note "Scenario 6: triage report + minimization preserving the failure"
    set +e
    "$COMPREG_BIN" verify --opts O2 --ad-hoc-source examples/runtime_failure.cpp | tail -2
    "$COMPREG_BIN" triage | tail -3
    set -e

    "$COMPREG_BIN" minimize --source examples/minimize_payload.cpp \
      --expected "$(printf '265\n86')" --opt O2 \
      | tee "$DEMO_DIR/minimize_demo.txt"
    note "minimized source (still fails against the trusted oracle):"
    cat "$(echo artifacts/minimize/minimize_payload/minimized.cpp)" || true
}

scenario_7() {
    note "Scenario 7: automated build/test pipeline (ctest + pytest)"
    if ! command -v ctest >/dev/null 2>&1; then
        echo "ctest not on PATH; using the compreg ctest entry (pip cmake provides it)"
    fi
    set +e
    "$COMPREG_BIN" ctest | tail -6
    echo "ctest exit=$?"
    set -e
    "$PY" -m pytest tests/unit -q 2>&1 | tail -2
}

scenario_all() {
    for n in 1 2 3 4 5 6 7; do
        "scenario_$n"
    done
}

case "${1:-all}" in
    1) scenario_1 ;;
    2) scenario_2 ;;
    3) scenario_3 ;;
    4) scenario_4 ;;
    5) scenario_5 ;;
    6) scenario_6 ;;
    7) scenario_7 ;;
    all) scenario_all ;;
    *) echo "unknown scenario: $1 (1..7 or all)"; exit 2 ;;
esac
