"""Integration tests: report export and triage artifacts end-to-end."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from conftest import have_gcc

from compreg.compiler.discovery import discover_compilers
from compreg.corpus.registry import PROJECT_ROOT, load_ad_hoc_test, load_curated_tests
from compreg.models import ResultCategory
from compreg.reporting.csv_report import CORRECTNESS_COLUMNS, correctness_rows, write_csv
from compreg.reporting.json_report import build_json_report, write_json
from compreg.verification.differential import verify_tests
from compreg.triage.classifier import collect_for_run


def _gcc_entry():
    return discover_compilers(["gcc"])[0]


@have_gcc
def test_complete_report_export(artifacts_tmp, tmp_path):
    entry = _gcc_entry()
    good = next(t for t in load_curated_tests() if t.test_id == "arithmetic_int_basic")
    broken = load_ad_hoc_test(
        PROJECT_ROOT / "examples" / "broken_bubble_sort.cpp",
        expected_stdout=(PROJECT_ROOT / "test_corpus" / "sorting" / "sorting_bubble_sort.expected").read_text(encoding="utf-8"),
    )
    outcomes, stats = verify_tests([good, broken], [entry], ["O2"], artifacts_tmp, "it_report")

    report = build_json_report(
        outcomes,
        [],
        metadata={
            "run_id": 1,
            "platform": "test",
            "artifacts": [str(artifacts_tmp / "runs")],
        },
    )
    json_path = write_json(report, str(tmp_path / "report.json"))
    document = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert document["summary"]["total"] == 2
    assert document["summary"]["passed"] == 1
    assert document["summary"]["output_mismatches"] == 1
    mismatch = next(t for t in document["tests"] if t["status"] == "OUTPUT_MISMATCH")
    assert mismatch["reproduction"]
    assert Path(mismatch["artifacts_dir"]).exists()

    csv_path = write_csv(correctness_rows(outcomes), tmp_path / "correctness.csv", CORRECTNESS_COLUMNS)
    rows = list(csv.DictReader(open(csv_path, newline="", encoding="utf-8")))
    assert len(rows) == 2
    statuses = {row["status"] for row in rows}
    assert statuses == {"PASS", "OUTPUT_MISMATCH"}


@have_gcc
def test_triage_report_contains_reproducible_commands(artifacts_tmp, tmp_path):
    entry = _gcc_entry()
    broken = load_ad_hoc_test(PROJECT_ROOT / "examples" / "runtime_failure.cpp", expected_stdout="")
    outcomes, stats = verify_tests([broken], [entry], ["O2"], artifacts_tmp, "it_triage")
    assert stats.nonzero_exits == 1

    written = collect_for_run(outcomes, tmp_path / "triage")
    assert len(written) == 1
    evidence = json.loads(written[0].read_text(encoding="utf-8"))
    assert evidence["test_id"]
    assert evidence["category"] == "NONZERO_EXIT"
    # Everything needed to reproduce:
    assert evidence["reproduction"]["compile_command"]
    assert evidence["reproduction"]["run_command"]
    assert evidence["reproduction"]["source_sha256"]
    assert evidence["configuration"]["opt_level"] == "O2"
    assert evidence["configuration"]["config_hash"]
    assert evidence["artifacts"]["expected_exit_code"] == 3
    # Observations vs hypotheses are separated in the schema.
    assert isinstance(evidence["observations"], list) and evidence["observations"]
    assert all(h.startswith("hypothesis") for h in evidence["hypotheses"])
