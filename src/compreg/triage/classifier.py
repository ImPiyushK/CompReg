"""Failure triage: evidence assembly for reproducible investigation.

Every finding carries the full reproduction context: test identity and
hash, compiler identity/configuration, exact commands, captured outputs,
artifact paths and (for benchmarks) baseline/current statistics. The report
makes a clear distinction between observed facts and hypotheses.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..execution.runner import classify_execution
from ..models import RegressionVerdict, TestOutcome
from ..util import format_command, now_iso, platform_string
from ..verification.differential import reproduction_command_line

FAILURE_TYPES = {
    "COMPILE_ERROR": "compile_failure",
    "OUTPUT_MISMATCH": "runtime_mismatch",
    "NONZERO_EXIT": "runtime_exit_failure",
    "TIMEOUT": "runtime_timeout",
    "EXECUTION_ERROR": "runtime_execution_error",
    "INFRASTRUCTURE_ERROR": "infrastructure_error",
}


@dataclass
class TriageItem:
    """One structured failure record, JSON-serializable as-is."""

    generated_at: str
    test_id: str
    category: str
    triage_class: str             # mapping of category -> triage namespace
    compiler: Dict[str, Any]
    configuration: Dict[str, Any]
    reproduction: Dict[str, Any]
    observations: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    baseline: Optional[Dict[str, Any]] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def build_triage(
    outcome: TestOutcome,
    *,
    regression: Optional[RegressionVerdict] = None,
    extra_observations: Optional[Sequence[str]] = None,
) -> TriageItem:
    """Turn a failure outcome (and optional benchmark regression) into evidence."""
    test = outcome.test_case
    identity = outcome.identity
    compile_result = outcome.compile_result
    execution_result = outcome.execution_result

    observations: List[str] = []
    if compile_result is not None:
        observations.append(
            f"compile exit code: {compile_result.returncode}; stderr lines: "
            f"{len((compile_result.stderr or '').splitlines())}"
        )
    if execution_result is not None:
        observations.append(
            f"execution exit code: {execution_result.returncode}, "
            f"elapsed {execution_result.elapsed_s:.3f}s, timed_out={execution_result.timed_out}"
        )
        if outcome.category.value in ("OUTPUT_MISMATCH",):
            observations.append(
                "actual stdout differs from the expected-output oracle "
                f"({test.oracle.kind.value})"
            )
        if outcome.category.value == "TIMEOUT":
            observations.append(f"process exceeded {test.timeout_s}s configured timeout")
    if extra_observations:
        observations.extend(extra_observations)

    # Hypotheses are labeled as such: plausible causes pending evidence.
    hypotheses: List[str] = []
    if outcome.category.value == "OUTPUT_MISMATCH":
        hypotheses.append(
            "hypothesis (unverified): the test program changed behavior; check the source diff "
            f"hash {outcome.source_sha256[:12]} against the recorded run history"
        )
    elif outcome.category.value == "COMPILE_ERROR":
        hypotheses.append(
            "hypothesis (unverified): the source no longer compiles under this standard/flags"
        )
    elif outcome.category.value == "TIMEOUT":
        hypotheses.append(
            f"hypothesis (unverified): workload grew (e.g. accidental O(n^2)); configured timeout {test.timeout_s}s"
        )
    elif outcome.category.value == "INFRASTRUCTURE_ERROR":
        hypotheses.append("hypothesis (unverified): environment/toolchain problem, not a compiler defect")

    regression_data: Optional[Dict[str, Any]] = None
    if regression is not None:
        regression_data = {
            "verdict": regression.verdict,
            "baseline_median_s": regression.baseline_median_s,
            "current_median_s": regression.current_median_s,
            "slowdown_pct": regression.slowdown_pct,
            "explanation": regression.explanation,
        }

    reproduction: Dict[str, Any] = {
        "compile_command": format_command(outcome.reproduction_compile)
        if outcome.reproduction_compile
        else None,
        "run_command": format_command(outcome.reproduction_run)
        if outcome.reproduction_run
        else None,
        "combined": reproduction_command_line(outcome) if outcome.is_failure else None,
        "source_sha256": outcome.source_sha256,
        "opt_level": outcome.opt_level,
        "std": identity.std,
    }

    return TriageItem(
        generated_at=now_iso(),
        test_id=test.test_id,
        category=outcome.category.value,
        triage_class=FAILURE_TYPES.get(outcome.category.value, outcome.category.value.lower()),
        compiler=identity.to_dict(),
        configuration={
            "opt_level": outcome.opt_level,
            "std": identity.std,
            "extra_flags": list(identity.extra_flags),
            "config_hash": outcome.config_hash,
            "host": platform_string(),
        },
        reproduction=reproduction,
        observations=observations,
        hypotheses=hypotheses,
        artifacts={
            "artifacts_dir": outcome.artifacts_dir,
            "expected_stdout": test.oracle.expected_stdout[:2000] if outcome.category.value == "OUTPUT_MISMATCH" else None,
            "actual_stdout": (execution_result.stdout[:2000] if execution_result else None),
            "actual_stderr": (execution_result.stderr[:2000] if execution_result else None),
            "compiler_stderr": (compile_result.stderr[:4000] if compile_result else None),
            "expected_exit_code": (execution_result.returncode if execution_result else None),
            "timeout_s": test.timeout_s,
        },
        baseline=regression_data,
    )


def write_triage_report(item: TriageItem, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(item.to_json(), encoding="utf-8")
    return path


def collect_for_run(
    outcomes: Sequence[TestOutcome],
    output_dir: Path,
    regressions: Optional[Sequence[RegressionVerdict]] = None,
    run_id: Optional[int] = None,
) -> List[Path]:
    """Write `triage_<test>_<config>.json` for every failed outcome.

    Returns the list of artifact paths.
    """
    regressions_by_key: Dict[tuple, RegressionVerdict] = {}
    for verdict in regressions or ():
        regressions_by_key[(verdict.test_id, verdict.config_hash)] = verdict

    written: List[Path] = []
    for outcome in outcomes:
        if not outcome.is_failure:
            continue
        item = build_triage(outcome, regression=regressions_by_key.get((outcome.test_case.test_id, outcome.config_hash)))
        name = f"triage_{outcome.test_case.test_id}_{outcome.identity.family}_{outcome.opt_level}.json"
        written.append(write_triage_report(item, output_dir / name))
    return written
