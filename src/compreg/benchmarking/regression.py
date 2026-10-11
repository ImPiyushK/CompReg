"""Baseline comparison and regression verdict logic.

Noise-aware decision rule (documented; evaluated by deterministic tests):
  A performance regression is reported iff ALL of the following hold:
    1. current and baseline sample counts are >= min_samples;
    2. baseline and current measurements are compatible (same test id,
       compiler configuration, benchmark version, machine profile);
    3. current_median > baseline_median * (1 + relative_threshold); and
    4. the excess exceeds max(absolute_threshold, k * baseline MAD).

  Rule (4) is the noise floor: an increase smaller than 3 MADs of the
  baseline, or below an absolute floor, is treated as scheduler noise and
  NOT labeled a regression. This prevents false positives from ordinary
  machine jitter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..models import BenchmarkStats, RegressionVerdict

VERDICT_REGRESSION = "regression"
VERDICT_NO_REGRESSION = "no_regression"
VERDICT_INSUFFICIENT = "insufficient_samples"
VERDICT_INCOMPATIBLE = "incompatible"
VERDICT_ERROR = "statistics_error"


@dataclass(frozen=True)
class RegressionPolicy:
    """Fixed decision thresholds used by `evaluate_regression`."""

    min_samples: int = 5
    rel_threshold: float = 0.20          # 20% median growth
    abs_threshold_s: float = 0.010       # 10 ms floor
    noise_k_mad: float = 3.0             # excess must exceed 3 * baseline MAD

    def __post_init__(self) -> None:
        if self.min_samples < 1:
            raise ValueError("min_samples must be >= 1")
        if self.rel_threshold < 0 or self.abs_threshold_s < 0 or self.noise_k_mad < 0:
            raise ValueError("thresholds must be >= 0")

    def noise_floor_s(self, baseline_mad: Optional[float]) -> float:
        """Absolute difference that must be exceeded, beyond measurement noise."""
        floor = self.abs_threshold_s
        if baseline_mad is not None:
            floor = max(floor, self.noise_k_mad * baseline_mad)
        return floor

    def is_regression(
        self,
        baseline_median: Optional[float],
        current_median: Optional[float],
        baseline_mad: Optional[float] = None,
        baseline_samples: Optional[int] = None,
        current_samples: Optional[int] = None,
    ) -> bool:
        """Strict boolean rule used by the verdict machinery and unit tests."""
        if baseline_median is None or current_median is None:
            return False
        if baseline_samples is not None and baseline_samples < self.min_samples:
            return False
        if current_samples is not None and current_samples < self.min_samples:
            return False
        relative_excess = current_median > baseline_median * (1.0 + self.rel_threshold)
        absolute_excess = (current_median - baseline_median) > self.noise_floor_s(baseline_mad)
        return bool(relative_excess and absolute_excess)


@dataclass
class CompatibilityCheck:
    compatible: bool
    reason: Optional[str] = None


def check_compatibility(
    *,
    baseline_test_id: str,
    current_test_id: str,
    baseline_config_hash: str,
    current_config_hash: str,
    baseline_benchmark_version: str,
    current_benchmark_version: str,
    baseline_host: Optional[str] = None,
    current_host: Optional[str] = None,
    require_same_host: bool = True,
) -> CompatibilityCheck:
    """Guard against silently comparing incompatible measurements."""
    if baseline_test_id != current_test_id:
        return CompatibilityCheck(False, f"test id differs: {baseline_test_id!r} vs {current_test_id!r}")
    if baseline_config_hash != current_config_hash:
        return CompatibilityCheck(
            False,
            "compiler configuration differs (optimization level, compiler version or flags)",
        )
    if baseline_benchmark_version != current_benchmark_version:
        return CompatibilityCheck(
            False,
            f"benchmark version differs: {baseline_benchmark_version!r} vs "
            f"{current_benchmark_version!r}",
        )
    if require_same_host and baseline_host and current_host and baseline_host != current_host:
        return CompatibilityCheck(
            False,
            f"machine profile differs: {baseline_host!r} vs {current_host!r} "
            "(baselines only transfer to the same machine)",
        )
    return CompatibilityCheck(True)


def evaluate_regression(
    *,
    policy: RegressionPolicy,
    test_id: str,
    config_hash: str,
    baseline: BenchmarkStats,
    current: BenchmarkStats,
    compatible: bool = True,
    incompatibility_reason: Optional[str] = None,
) -> RegressionVerdict:
    """Apply the documented rule to one baseline/current pair."""
    if not compatible:
        return RegressionVerdict(
            test_id=test_id,
            config_hash=config_hash,
            compatible=False,
            incompatibility_reason=incompatibility_reason,
            baseline_median_s=baseline.median_s,
            current_median_s=current.median_s,
            baseline_samples=baseline.samples,
            current_samples=current.samples,
            slowdown_pct=None,
            verdict=VERDICT_INCOMPATIBLE,
            explanation=incompatibility_reason or "baseline incompatible",
        )
    if baseline.samples < policy.min_samples or current.samples < policy.min_samples:
        return RegressionVerdict(
            test_id=test_id,
            config_hash=config_hash,
            compatible=True,
            incompatibility_reason=None,
            baseline_median_s=baseline.median_s,
            current_median_s=current.median_s,
            baseline_samples=baseline.samples,
            current_samples=current.samples,
            slowdown_pct=None,
            verdict=VERDICT_INSUFFICIENT,
            explanation=(
                f"need >= {policy.min_samples} samples (baseline {baseline.samples}, "
                f"current {current.samples}); refusing to call this a regression"
            ),
        )

    slowdown = None
    verdict = VERDICT_NO_REGRESSION
    explanation = "within thresholds"
    if baseline.median_s > 0:
        slowdown = (current.median_s / baseline.median_s - 1.0) * 100.0
        try:
            regression = policy.is_regression(
                baseline.median_s,
                current.median_s,
                baseline_mad=baseline.mad_s,
                baseline_samples=baseline.samples,
                current_samples=current.samples,
            )
        except (ValueError, ZeroDivisionError) as exc:  # defensive
            return RegressionVerdict(
                test_id=test_id,
                config_hash=config_hash,
                compatible=True,
                incompatibility_reason=None,
                baseline_median_s=baseline.median_s,
                current_median_s=current.median_s,
                baseline_samples=baseline.samples,
                current_samples=current.samples,
                slowdown_pct=None,
                verdict=VERDICT_ERROR,
                explanation=f"statistics error: {exc}",
            )
        if regression:
            verdict = VERDICT_REGRESSION
            explanation = (
                f"median {current.median_s:.4f}s vs baseline {baseline.median_s:.4f}s "
                f"({slowdown:+.1f}%), noise floor {policy.noise_floor_s(baseline.mad_s):.4f}s"
            )
    return RegressionVerdict(
        test_id=test_id,
        config_hash=config_hash,
        compatible=True,
        incompatibility_reason=None,
        baseline_median_s=baseline.median_s,
        current_median_s=current.median_s,
        baseline_samples=baseline.samples,
        current_samples=current.samples,
        slowdown_pct=slowdown,
        verdict=verdict,
        explanation=explanation,
    )
