#!/usr/bin/env python3
"""Scenario 4 helper: deterministic statistical-regression demo.

Validates the noise-aware regression rule with controlled measurement data.
This makes NO wall-clock performance claims - it validates the algorithm.
"""

from __future__ import annotations

import random

from compreg.benchmarking.regression import RegressionPolicy, evaluate_regression
from compreg.benchmarking.statistics import compute_stats


def main() -> int:
    random.seed(8675309)
    policy = RegressionPolicy(
        min_samples=5, rel_threshold=0.20, abs_threshold_s=0.010, noise_k_mad=3.0
    )

    base = compute_stats([0.100 + random.uniform(-0.002, 0.002) for _ in range(9)])
    same = compute_stats([0.101 + random.uniform(-0.002, 0.002) for _ in range(9)])
    noisy = compute_stats([0.115 + random.uniform(-0.004, 0.004) for _ in range(9)])
    slow = compute_stats([0.160 + random.uniform(-0.002, 0.002) for _ in range(9)])
    few = compute_stats([0.16, 0.17, 0.15])

    print("baseline median        :", round(base.median_s, 5), "MAD", round(base.mad_s, 5))
    print("+1% jitter verdict     :", evaluate_regression(
        policy=policy, test_id="demo", config_hash="c", baseline=base, current=same).verdict)
    print("+15% inside noise floor:", evaluate_regression(
        policy=policy, test_id="demo", config_hash="c", baseline=base, current=noisy).verdict)
    print("+60% clear regression  :", evaluate_regression(
        policy=policy, test_id="demo", config_hash="c", baseline=base, current=slow).verdict)
    print("3 samples only         :", evaluate_regression(
        policy=policy, test_id="demo", config_hash="c", baseline=base, current=few).verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
