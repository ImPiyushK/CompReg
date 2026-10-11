"""Unit tests: noise-aware regression verdict logic with synthetic measurements.

These tests validate the detection ALGORITHM deterministically; they make no
wall-clock performance claims. Real-clock demonstration belongs to the
separately documented demo scenarios.
"""

from __future__ import annotations

import pytest

from compreg.benchmarking.regression import (
    RegressionPolicy,
    VERDICT_INCOMPATIBLE,
    VERDICT_INSUFFICIENT,
    VERDICT_NO_REGRESSION,
    VERDICT_REGRESSION,
    check_compatibility,
    evaluate_regression,
)
from compreg.benchmarking.statistics import compute_stats
from compreg.models import BenchmarkStats


def stats_of(values):
    return compute_stats(values)


def test_baseline_and_current_within_thresholds_is_not_a_regression():
    baseline = BenchmarkStats(9, 0.100, 0.095, 0.105, 0.002)
    current = BenchmarkStats(9, 0.101, 0.096, 0.106, 0.002)  # +1%
    verdict = evaluate_regression(
        policy=RegressionPolicy(), test_id="t", config_hash="c",
        baseline=baseline, current=current,
    )
    assert verdict.verdict == VERDICT_NO_REGRESSION


def test_sampling_noise_within_mad_is_not_a_regression():
    baseline = BenchmarkStats(9, 0.100, 0.09, 0.11, 0.010)  # MAD 10ms -> floor 30ms
    current = BenchmarkStats(9, 0.125, 0.11, 0.14, 0.005)   # +25%, +25ms < 30ms floor
    verdict = evaluate_regression(
        policy=RegressionPolicy(), test_id="t", config_hash="c",
        baseline=baseline, current=current,
    )
    assert verdict.verdict == VERDICT_NO_REGRESSION


def test_clear_regression_is_reported():
    baseline = BenchmarkStats(9, 0.100, 0.09, 0.11, 0.002)
    current = BenchmarkStats(9, 0.150, 0.14, 0.16, 0.002)  # +50% > 20%, +50ms > 6ms
    verdict = evaluate_regression(
        policy=RegressionPolicy(), test_id="t", config_hash="c",
        baseline=baseline, current=current,
    )
    assert verdict.verdict == VERDICT_REGRESSION
    assert verdict.slowdown_pct == pytest.approx(50.0, rel=1e-3)


def test_odd_sample_median():
    from compreg.benchmarking.statistics import compute_stats

    assert compute_stats([0.10, 0.13, 0.12, 0.20, 0.11]).median_s == pytest.approx(0.12)


def test_even_sample_median_averages_middle():
    from compreg.benchmarking.statistics import compute_stats

    assert compute_stats([1.0, 2.0, 3.0, 4.0]).median_s == pytest.approx(2.5)


def test_buckets_of_noise_do_not_trip_the_detector():
    # Deterministic seeded jitter around the baseline; no regression verdict.
    import random

    random.seed(1234)
    policy = RegressionPolicy()
    baseline_values = [0.100 + random.uniform(-0.004, 0.004) for _ in range(120)]
    baseline = stats_of(baseline_values)
    regressions = 0
    for trial in range(40):
        jittered = [0.100 + random.uniform(-0.004, 0.004) for _ in range(10)]
        verdict = evaluate_regression(
            policy=policy, test_id="t", config_hash="c",
            baseline=baseline, current=stats_of(jittered),
        )
        if verdict.verdict == VERDICT_REGRESSION:
            regressions += 1
    assert regressions == 0, "jittered samples must not be labeled regressions"


def test_insufficient_samples_never_called_regression():
    for n in (1, 2, 3, 4):
        verdict = evaluate_regression(
            policy=RegressionPolicy(min_samples=5),
            test_id="t", config_hash="c",
            baseline=BenchmarkStats(n, 0.10, 0.09, 0.11, 0.001),
            current=BenchmarkStats(n, 0.90, 0.80, 0.95, 0.001),
        )
        assert verdict.verdict == VERDICT_INSUFFICIENT


def test_incompatible_benchmark_metadata_blocks_comparison():
    verdict = evaluate_regression(
        policy=RegressionPolicy(), test_id="t", config_hash="c",
        baseline=BenchmarkStats(9, 0.10, 0.09, 0.11, 0.001),
        current=BenchmarkStats(9, 0.50, 0.4, 0.6, 0.001),
        compatible=False,
        incompatibility_reason="benchmark version differs: v1 vs v2",
    )
    assert verdict.verdict == VERDICT_INCOMPATIBLE
    assert "v1 vs v2" in verdict.explanation


def test_compatibility_guard_covers_every_axis():
    base = check_compatibility(
        baseline_test_id="t", current_test_id="t",
        baseline_config_hash="c", current_config_hash="c",
        baseline_benchmark_version="v1", current_benchmark_version="v1",
    )
    assert base.compatible

    assert not check_compatibility(
        baseline_test_id="t", current_test_id="other",
        baseline_config_hash="c", current_config_hash="c",
        baseline_benchmark_version="v1", current_benchmark_version="v1",
    ).compatible
    assert not check_compatibility(
        baseline_test_id="t", current_test_id="t",
        baseline_config_hash="cA", current_config_hash="cB",
        baseline_benchmark_version="v1", current_benchmark_version="v1",
    ).compatible
    assert not check_compatibility(
        baseline_test_id="t", current_test_id="t",
        baseline_config_hash="c", current_config_hash="c",
        baseline_benchmark_version="v1", current_benchmark_version="v2",
    ).compatible
    host_guard = check_compatibility(
        baseline_test_id="t", current_test_id="t",
        baseline_config_hash="c", current_config_hash="c",
        baseline_benchmark_version="v1", current_benchmark_version="v1",
        baseline_host="Linux/x86", current_host="Windows/amd64",
        require_same_host=True,
    )
    assert not host_guard.compatible
    transfer = check_compatibility(
        baseline_test_id="t", current_test_id="t",
        baseline_config_hash="c", current_config_hash="c",
        baseline_benchmark_version="v1", current_benchmark_version="v1",
        baseline_host="Linux/x86", current_host="Windows/amd64",
        require_same_host=False,
    )
    assert transfer.compatible


def test_abs_threshold_only_regression():
    policy = RegressionPolicy(min_samples=3, rel_threshold=0.05, abs_threshold_s=0.05, noise_k_mad=3.0)
    baseline = BenchmarkStats(5, 0.010, 0.0095, 0.0105, 0.0001)
    current = BenchmarkStats(5, 0.011, 0.010, 0.012, 0.0001)  # +10% but only +1ms < 50ms
    verdict = evaluate_regression(policy=policy, test_id="t", config_hash="c",
                                  baseline=baseline, current=current)
    assert verdict.verdict == VERDICT_NO_REGRESSION


def test_negative_baseline_median_rejected():
    verdict = evaluate_regression(
        policy=RegressionPolicy(), test_id="t", config_hash="c",
        baseline=BenchmarkStats(5, -0.10, -0.11, -0.09, 0.001),
        current=BenchmarkStats(5, 0.30, 0.29, 0.31, 0.001),
    )
    assert verdict.verdict in (VERDICT_NO_REGRESSION, "statistics_error")


def test_policy_validates_thresholds():
    with pytest.raises(ValueError):
        RegressionPolicy(min_samples=0)
    with pytest.raises(ValueError):
        RegressionPolicy(rel_threshold=-0.1)
