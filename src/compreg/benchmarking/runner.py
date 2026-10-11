"""Repeated wall-clock benchmark execution.

Measurement model (documented honestly):
  * Each sample is the wall time of one full process execution, taken with
    time.perf_counter around subprocess.run. Process startup and filesystem
    overhead are therefore included in every sample.
  * This is appropriate for the bundled benchmark programs, whose runtime
    work dominates startup cost (tens of ms to seconds). For shorter
    programs, startup/noise dominates - the docs state this explicitly.
  * Warm-up samples run but are discarded. All measured samples are kept;
    aggregation uses median/MAD, which tolerates scheduler outliers.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional

from ..execution.runner import ProgramRunner, RunRequest
from ..models import BenchmarkStats

log = logging.getLogger(__name__)


def _perf() -> float:
    return time.perf_counter()


def measure_samples(
    binary: str,
    reps: int,
    warmup: int = 0,
    timeout_s: float = 60.0,
    clock: Optional[Callable[[], float]] = None,
    executor: Optional[ProgramRunner] = None,
) -> List[float]:
    """Measure `reps` executions (plus discarded warm-ups) of one binary.

    `clock` and `executor` are injection points for deterministic tests.
    A timed-out run aborts measurement (infrastructure/behavior problem, not
    a performance datapoint); the caller classifies it.
    """
    if reps < 1:
        raise ValueError("reps must be >= 1")
    if warmup < 0:
        raise ValueError("warmup must be >= 0")

    runner = executor or ProgramRunner()
    clock_fn = clock or _perf
    samples: List[float] = []

    total_runs = warmup + reps
    for index in range(total_runs):
        start = clock_fn()
        request = RunRequest(binary=binary, timeout_s=timeout_s)
        result = runner.run(request)
        elapsed = clock_fn() - start
        if result.timed_out:
            raise TimeoutError(
                f"benchmark run #{index + 1} exceeded {timeout_s} s timeout"
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"benchmark run #{index + 1} failed with exit code {result.returncode}"
            )
        if index >= warmup:
            samples.append(elapsed)
    return samples


def run_with_stats(
    binary: str,
    reps: int,
    warmup: int = 0,
    timeout_s: float = 60.0,
    executor: Optional[ProgramRunner] = None,
) -> tuple[List[float], BenchmarkStats]:
    """Measure and aggregate; convenience wrapper used by the CLI."""
    from ..benchmarking.statistics import compute_stats

    samples = measure_samples(binary, reps, warmup, timeout_s, executor=executor)
    return samples, compute_stats(samples)
