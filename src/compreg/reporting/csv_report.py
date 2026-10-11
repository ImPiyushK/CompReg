"""CSV export: one row per (test, compiler, config) outcome or benchmark."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Sequence

from ..models import TestOutcome
from ..verification.differential import reproduction_command_line

CORRECTNESS_COLUMNS = [
    "test_id",
    "category",
    "compiler_family",
    "compiler_version",
    "opt_level",
    "status",
    "message",
    "exit_code",
    "elapsed_s",
    "config_hash",
    "source_sha256",
    "artifacts_dir",
    "reproduction",
]

BENCHMARK_COLUMNS = [
    "test_id",
    "category",
    "compiler_family",
    "compiler_version",
    "opt_level",
    "samples",
    "median_s",
    "min_s",
    "max_s",
    "mad_s",
    "row_kind",
]


def _version_label(outcome: TestOutcome) -> str:
    numeric = ".".join(
        str(part)
        for part in (
            outcome.identity.version_major,
            outcome.identity.version_minor,
            outcome.identity.version_patch,
        )
        if part is not None
    )
    if numeric:
        return numeric
    # Database-reconstructed rows carry the version text when available.
    return outcome.identity.version_text or ""


def correctness_rows(outcomes: Sequence[TestOutcome]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for outcome in outcomes:
        outcome_row = {
            "test_id": outcome.test_case.test_id,
            "category": outcome.test_case.category,
            "compiler_family": outcome.identity.family,
            "compiler_version": _version_label(outcome),
            "opt_level": outcome.opt_level,
            "status": outcome.category.value,
            "message": outcome.message,
            "exit_code": outcome.execution_result.returncode
            if outcome.execution_result is not None
            else None,
            "elapsed_s": round(outcome.execution_result.elapsed_s, 6)
            if outcome.execution_result is not None
            else None,
            "config_hash": outcome.config_hash,
            "source_sha256": outcome.source_sha256,
            "artifacts_dir": outcome.artifacts_dir,
            "reproduction": reproduction_command_line(outcome) if outcome.is_failure else None,
            "row_kind": "correctness",
        }
        rows.append(outcome_row)
    return rows


def benchmark_rows(benchmark_stat_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pass through DB-shaped stat rows (already flat)."""
    rows: List[Dict[str, Any]] = []
    for stat in benchmark_stat_rows:
        family, _, _ = None, None, None
        rows.append(
            {
                "test_id": stat["test_id"],
                "category": "benchmark",
                "compiler_family": stat.get("compiler_family", ""),
                "compiler_version": stat.get("compiler_version", ""),
                "opt_level": stat.get("opt_level", ""),
                "samples": stat["samples"],
                "median_s": stat["median_s"],
                "min_s": stat["min_s"],
                "max_s": stat["max_s"],
                "mad_s": stat["mad_s"],
                "row_kind": "benchmark",
            }
        )
    return rows


def write_csv(
    rows: Sequence[Dict[str, Any]],
    path: str | Path,
    columns: Sequence[str],
) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return str(target)
