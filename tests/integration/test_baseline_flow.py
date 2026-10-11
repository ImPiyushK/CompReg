"""Integration tests: persistence, baseline flows and injected regressions.

Regression detection is validated with controlled (injected) measurements so
the suite is deterministic; real wall-clock benchmarks belong to the demo
scenarios, not here.
"""

from __future__ import annotations

import json

import pytest

from conftest import have_gcc
from compreg.benchmarking.regression import (
    RegressionPolicy,
    evaluate_regression,
    VERDICT_REGRESSION,
)
from compreg.benchmarking.statistics import compute_stats
from compreg.compiler.discovery import discover_compilers
from compreg.corpus.registry import load_curated_tests
from compreg.models import BenchmarkStats, ResultCategory, RunMeta
from compreg.verification.differential import verify_tests
from compreg.storage.database import initialize_database
from compreg.storage.repository import Repository


def _gcc_entry():
    return discover_compilers(["gcc"])[0]


@have_gcc
def test_verify_results_persist_and_query_back(artifacts_tmp, tmp_path):
    db = initialize_database(tmp_path / "compreg.db")
    repo = Repository(db)
    entry = _gcc_entry()
    tests = [t for t in load_curated_tests() if t.test_id in ("arithmetic_int_basic", "arrays_histogram")]
    outcomes, _ = verify_tests([t for t in tests], [entry], ["O2"], artifacts_tmp, "it_dbrun")

    from compreg.models import RunMeta
    from compreg.models import RunMeta as _RunMeta

    config = None
    meta = _RunMeta.start({"compreg": "test"})
    run_id = repo.insert_run(meta)
    for outcome in outcomes:
        repo.insert_correctness_result(
            run_id, outcome.test_case, outcome.config_hash, outcome.category.value,
            message=outcome.message, source_hash=outcome.source_sha256,
        )
    rows = repo.results_for_run(run_id)
    assert len(rows) == 2
    assert all(row["category"] == "PASS" for row in rows)
    # The test-case rows record source hashes for provenance.
    for row in rows:
        assert row["test_id"] in ("arithmetic_int_basic", "arrays_histogram")
    repo.finish_run(run_id, "completed")
    stored_meta = repo.get_run(run_id)
    assert stored_meta["status"] == "completed"
    assert json.loads(stored_meta["tool_json"]).get("compreg")
    db.close()


def test_injected_regression_flow_through_database(tmp_path):
    """Simulated 'commit slowed the benchmark down' flow with injected samples.

    The samples are explicitly marked origin=inject in the database so nobody
    can mistake them for measured wall-clock data.
    """
    db = initialize_database(tmp_path / "compreg.db")
    repo = Repository(db)
    meta = RunMeta.start({"compreg": "test"})
    baseline_run = repo.insert_run(meta)
    repo.finish_run(baseline_run, "completed")

    fast_samples = [0.100, 0.101, 0.099, 0.100, 0.102, 0.100, 0.101]
    slow_samples = [0.280, 0.285, 0.279, 0.300, 0.290, 0.275, 0.284]

    baseline_stats = compute_stats(fast_samples)
    repo.insert_benchmark_stat(
        baseline_run, "demo_test", "cfg1", "v1", baseline_stats, warmup=2, origin="inject"
    )
    repo.insert_benchmark_samples(baseline_run, "demo_test", "cfg1", fast_samples, origin="inject")

    baseline_id = repo.upsert_baseline(
        test_id="demo_test", config_hash="cfg1", benchmark_version="v1",
        stats=baseline_stats, source_run_id=baseline_run, host=meta.host,
    )

    # A later run with the regressed build.
    later_meta = RunMeta.start({})
    later_run = repo.insert_run(later_meta)
    repo.finish_run(later_run, "completed")
    current_stats = compute_stats(slow_samples)
    repo.insert_benchmark_stat(
        later_run, "demo_test", "cfg1", "v1", current_stats, warmup=2, origin="inject"
    )
    repo.insert_benchmark_samples(later_run, "demo_test", "cfg1", slow_samples, origin="inject")

    # Compare (the CLI-compare rule, expressed through the library API).
    verdict = evaluate_regression(
        policy=RegressionPolicy(), test_id="demo_test", config_hash="cfg1",
        baseline=baseline_stats, current=current_stats,
    )
    assert verdict.verdict == VERDICT_REGRESSION
    assert verdict.slowdown_pct > 100.0
    repo.insert_regression(
        run_id=later_run, test_id="demo_test", config_hash="cfg1", baseline_id=baseline_id,
        baseline_median=baseline_stats.median_s, current_median=current_stats.median_s,
        slowdown_pct=verdict.slowdown_pct, verdict=verdict.verdict,
        evidence={"verdict_explanation": verdict.explanation, "origin": "injected-samples"},
    )

    history = repo.regression_history("demo_test")
    assert len(history) == 1
    assert history[0]["verdict"] == VERDICT_REGRESSION
    # The stored evidence keeps the injected origin visible.
    loaded = json.loads(history[0]["evidence_json"])
    assert loaded["origin"] == "injected-samples"
    db.close()


def test_baseline_guard_rejects_foreign_context(tmp_path):
    db = initialize_database(tmp_path / "compreg.db")
    repo = Repository(db)
    meta = RunMeta.start({})
    run_id = repo.insert_run(meta)
    repo.finish_run(run_id, "completed")
    repo.upsert_baseline(
        test_id="t", config_hash="c", benchmark_version="v1",
        stats=BenchmarkStats(7, 0.1, 0.09, 0.11, 0.001),
        source_run_id=run_id, host="hostA",
    )
    assert repo.latest_baseline("t", "c", "v1", "hostB") is None
    assert repo.latest_baseline("t", "OTHER", "v1", "hostA") is None
    assert repo.latest_baseline("t", "c", "v2", "hostA") is None
    db.close()
