"""Benchmark statistics.

All functions are pure and tested against hand-computed values. Use
mededian/MAD (robust to outliers from scheduler hiccups) instead of mean/sd
for small sample counts.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence

from ..models import BenchmarkStats


def compute_stats(samples: Iterable[float]) -> BenchmarkStats:
    """Compute robustness-friendly statistics for a wall-clock sample list.

    Requires at least one sample. Samples are clamped to positive values;
    negative or NaN inputs raise ValueError (they indicate instrumentation
    bugs, not real timings).
    """
    values: List[float] = [float(s) for s in samples]
    if not values:
        raise ValueError("cannot compute statistics without samples")
    for value in values:
        if value != value or value != abs(value) or value == float("inf"):
            raise ValueError(f"invalid timing sample: {value}")

    ordered = sorted(values)
    median = _median(ordered)
    mad = _median(sorted(abs(x - median) for x in ordered))
    return BenchmarkStats(
        samples=len(ordered),
        median_s=median,
        min_s=ordered[0],
        max_s=ordered[-1],
        mad_s=mad,
    )


def _median(ordered: Sequence[float]) -> float:
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def slowdown_pct(baseline_median: float, current_median: float) -> float:
    """Percent slowdown of current vs baseline (negative means faster)."""
    if baseline_median <= 0:
        raise ValueError("baseline_median must be > 0")
    return (current_median / baseline_median - 1.0) * 100.0
