"""JSON report generation with a stable, documented schema.

Schema: compreg.report.v1 (docs/reporting.md). Keys are fixed; consumers
can rely on them. Unknown data is nested under `detail` so the contract
survives backward-compatible extension.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..benchmarking.regression import RegressionVerdict
from ..models import TestOutcome
from ..verification.differential import reproduction_command_line

REPORT_SCHEMA = "compreg.report.v1"

_TYPES = [
    "passed",
    "failed",
    "compile_errors",
    "output_mismatches",
    "nonzero_exits",
    "timeouts",
    "execution_errors",
    "infrastructure_errors",
    "regressions",
    "skipped",
]


def summarize(outcomes: Sequence[TestOutcome]) -> Dict[str, Any]:
    """Public summarizer used by the CLI text views."""
    from ..models import ResultCategory

    summary: Dict[str, Any] = {name: 0 for name in _TYPES}
    summary["total"] = len(outcomes)
    for outcome in outcomes:
        name = {
            ResultCategory.PASS: "passed",
            ResultCategory.COMPILE_ERROR: "compile_errors",
            ResultCategory.OUTPUT_MISMATCH: "output_mismatches",
            ResultCategory.NONZERO_EXIT: "nonzero_exits",
            ResultCategory.TIMEOUT: "timeouts",
            ResultCategory.EXECUTION_ERROR: "execution_errors",
            ResultCategory.INFRASTRUCTURE_ERROR: "infrastructure_errors",
            ResultCategory.SKIPPED: "skipped",
        }.get(outcome.category)
        if name:
            summary[name] += 1
    summary["failed"] = summary["total"] - summary["passed"] - summary["skipped"]
    return summary


def _outcome_record(outcome: TestOutcome) -> Dict[str, Any]:
    test = outcome.test_case
    record: Dict[str, Any] = {
        "test_id": test.test_id,
        "category": test.category,
        "source_path": test.source_path,
        "compiler": {
            "family": outcome.identity.family,
            "name": outcome.identity.display_name,
            "executable": outcome.identity.executable,
            "target": outcome.identity.target,
        },
        "opt_level": outcome.opt_level,
        "std": outcome.identity.std,
        "config_hash": outcome.config_hash,
        "source_sha256": outcome.source_sha256,
        "status": outcome.category.value,
        "message": outcome.message,
        "timeout_s": test.timeout_s,
        "detail": {},
    }
    if outcome.execution_result:
        record["detail"] = {
            "exit_code": outcome.execution_result.returncode,
            "elapsed_s": round(outcome.execution_result.elapsed_s, 6),
            "timed_out": outcome.execution_result.timed_out,
        }
    if outcome.is_failure:
        record["reproduction"] = reproduction_command_line(outcome)
        record["artifacts_dir"] = outcome.artifacts_dir
    return record


def _regression_record(verdict: RegressionVerdict) -> Dict[str, Any]:
    record = verdict.to_dict()
    record["verdict"] = verdict.verdict
    return record


def build_json_report(
    outcomes: Sequence[TestOutcome],
    regressions: Sequence[RegressionVerdict],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble the full report document following compreg.report.v1."""
    summary = _summarize_with_regressions(outcomes, regressions)
    report: Dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "metadata": metadata,
        "summary": summary,
        "tests": [_outcome_record(o) for o in outcomes],
        "regressions": [_regression_record(v) for v in regressions],
        "artifacts": metadata.get("artifacts", []),
    }
    return report


def _summarize_with_regressions(
    outcomes: Sequence[TestOutcome],
    regressions: Sequence[RegressionVerdict],
) -> Dict[str, int]:
    from ..models import ResultCategory

    summary: Dict[str, int] = {name: 0 for name in _TYPES}
    summary["total"] = len(outcomes)
    for outcome in outcomes:
        name = {
            ResultCategory.PASS: "passed",
            ResultCategory.COMPILE_ERROR: "compile_errors",
            ResultCategory.OUTPUT_MISMATCH: "output_mismatches",
            ResultCategory.NONZERO_EXIT: "nonzero_exits",
            ResultCategory.TIMEOUT: "timeouts",
            ResultCategory.EXECUTION_ERROR: "execution_errors",
            ResultCategory.INFRASTRUCTURE_ERROR: "infrastructure_errors",
            ResultCategory.SKIPPED: "skipped",
        }.get(outcome.category)
        if name:
            summary[name] += 1
    summary["failed"] = summary["total"] - summary["passed"] - summary["skipped"]
    summary["regressions"] = sum(1 for v in regressions if v.verdict == "regression")
    return summary


def write_json(report: Dict[str, Any], path: str) -> str:
    import json

    import pathlib

    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return str(target)
