"""Unit tests: benchmark statistics (hand-computed values)."""

from __future__ import annotations

import pytest

from compreg.benchmarking.statistics import compute_stats, slowdown_pct


def test_odd_sample_median():
    stats = compute_stats([0.10, 0.13, 0.12, 0.20, 0.11])
    assert stats.median_s == pytest.approx(0.12)
    assert stats.min_s == pytest.approx(0.10)
    assert stats.max_s == pytest.approx(0.20)


def test_even_sample_median_averages_middle():
    stats = compute_stats([1.0, 2.0, 3.0, 4.0])
    assert stats.median_s == pytest.approx(2.5)


def test_mad_known_value():
    # samples 1..5 -> median 3 -> absolute deviations 2,1,0,1,2 -> MAD 1
    stats = compute_stats([1.0, 2.0, 3.0, 4.0, 5.0])
    assert stats.mad_s == pytest.approx(1.0)


def test_mad_robust_to_outliers():
    # 5 samples around 0.5 plus one extreme outlier: the median is unchanged
    # and MAD moves only marginally (unlike mean-based dispersion).
    clean = [0.49, 0.50, 0.51, 0.50, 0.50]
    noisy = clean + [9.9]
    base = compute_stats(clean)
    outliered = compute_stats(noisy)
    assert outliered.median_s == base.median_s
    assert outliered.mad_s <= base.mad_s + 0.01
    assert outliered.max_s == pytest.approx(9.9)  # max reflects the outlier


def test_single_sample():
    stats = compute_stats([0.42])
    assert stats.median_s == pytest.approx(0.42)
    assert stats.min_s == stats.max_s == pytest.approx(0.42)
    assert stats.mad_s == pytest.approx(0.0)


def test_empty_samples_rejected():
    with pytest.raises(ValueError, match="without samples"):
        compute_stats([])


def test_invalid_samples_rejected():
    for bad in ([-1.0], [0.0 if False else float("nan")], [float("inf")]):
        with pytest.raises(ValueError, match="invalid timing"):
            compute_stats(bad)


def test_slowdown_pct_math():
    assert slowdown_pct(0.10, 0.15) == pytest.approx(50.0)
    assert slowdown_pct(0.10, 0.05) == pytest.approx(-50.0)
    with pytest.raises(ValueError):
        slowdown_pct(0.0, 0.1)
