"""Unit tests: report serialization (JSON schema stability, CSV rows)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from compreg.benchmarking.regression import RegressionVerdict
from compreg.models import (
    CompilerIdentity,
    ExecutionResult,
    OracleKind,
    OracleSpec,
    ResultCategory,
    TestCase,
    TestOutcome,
)
from compreg.reporting.csv_report import (
    CORRECTNESS_COLUMNS,
    correctness_rows,
    write_csv,
)
from compreg.reporting.json_report import REPORT_SCHEMA, build_json_report


def _case(test_id: str = "t_alpha") -> TestCase:
    return TestCase(
        test_id=test_id,
        source_path="test_corpus/x/../x.cpp",
        category="arithmetic",
        description="demo",
        oracle=OracleSpec(kind=OracleKind.EXACT, expected_stdout="1\n"),
        timeout_s=3.0,
    )


def _outcome(category: ResultCategory = ResultCategory.PASS) -> TestOutcome:
    case = _case()
    identity = CompilerIdentity(
        family="gcc", executable="/usr/bin/g++", version_text="g++ (x) 13.3.0",
        version_major=13, version_minor=3, version_patch=0, target="x86_64",
    )
    outcome = TestOutcome(
        test_case=case,
        identity=identity,
        opt_level="O2",
        config_hash="cfg123",
        category=category,
        message="first differing line #1: expected '1', got '2'" if category is ResultCategory.OUTPUT_MISMATCH else "",
        source_sha256="deadbeef" * 8,
    )
    if category in (ResultCategory.OUTPUT_MISMATCH, ResultCategory.PASS):
        outcome.execution_result = ExecutionResult(
            ok=category is ResultCategory.PASS,
            command=["./bin"],
            stdout="2\n" if category is ResultCategory.OUTPUT_MISMATCH else "1\n",
            stderr="",
            returncode=0,
            elapsed_s=0.01,
        )
        outcome.reproduction_run = ["./bin"]
        outcome.artifacts_dir = "/artifacts/x"
    return outcome


def test_json_report_schema_and_counts():
    outcomes = [
        _outcome(ResultCategory.PASS),
        _outcome(ResultCategory.OUTPUT_MISMATCH),
        _outcome(ResultCategory.SKIPPED),
    ]
    regression = RegressionVerdict(
        test_id="bench", config_hash="c1", compatible=True, incompatibility_reason=None,
        baseline_median_s=0.1, current_median_s=0.3,
        baseline_samples=7, current_samples=7, slowdown_pct=200.0,
        verdict="regression", explanation="demo",
    )
    report = build_json_report(outcomes, [regression], {"run_id": 3})
    assert report["schema"] == REPORT_SCHEMA == "compreg.report.v1"
    summary = report["summary"]
    assert summary["total"] == 3
    assert summary["passed"] == 1
    assert summary["output_mismatches"] == 1
    assert summary["skipped"] == 1
    assert summary["failed"] == 1
    assert summary["regressions"] == 1
    assert report["metadata"]["run_id"] == 3
    failing_entries = [
        entry for entry in report["tests"]
        if entry["status"] not in ("PASS", "SKIPPED")
    ]
    assert failing_entries and all("reproduction" in entry for entry in failing_entries)


def test_json_report_json_serializable_and_stable():
    report = build_json_report([_outcome(ResultCategory.PASS)], [], {"run_id": 1})
    dumped_a = json.dumps(report, sort_keys=True)
    dumped_b = json.dumps(build_json_report([_outcome(ResultCategory.PASS)], [], {"run_id": 1}), sort_keys=True)
    assert dumped_a == dumped_b


def test_csv_rows_are_flat_and_complete(tmp_path: Path):
    outcomes = [_outcome(ResultCategory.PASS), _outcome(ResultCategory.OUTPUT_MISMATCH)]
    rows = correctness_rows(outcomes)
    assert len(rows) == 2
    for row in rows:
        assert set(row.keys()) >= set(CORRECTNESS_COLUMNS)
    assert rows[1]["status"] == "OUTPUT_MISMATCH"
    assert rows[1]["reproduction"]
    path = write_csv(rows, tmp_path / "out.csv", CORRECTNESS_COLUMNS)
    with open(path, newline="", encoding="utf-8") as handle:
        parsed = list(csv.DictReader(handle))
    assert len(parsed) == 2
    assert parsed[0]["test_id"] == "t_alpha"
    assert parsed[1]["status"] == "OUTPUT_MISMATCH"
