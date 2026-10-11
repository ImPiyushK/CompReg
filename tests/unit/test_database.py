"""Unit tests: database schema, versioning and repository behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from compreg.corpus.registry import load_curated_tests
from compreg.models import BenchmarkStats, CompilerIdentity, RunMeta
from compreg.storage.database import initialize_database
from compreg.storage.repository import Repository


@pytest.fixture()
def repo(tmp_path: Path):
    db = initialize_database(tmp_path / "compreg.db")
    repository = Repository(db)
    yield repository, db
    db.close()


def test_schema_version_recorded(repo):
    repository, db = repo
    assert db.schema_version() >= 1


def test_run_insert_and_finish(repo):
    repository, _ = repo
    meta = RunMeta.start({})
    run_id = repository.insert_run(meta)
    assert run_id >= 1
    assert repository.get_run(run_id)["status"] == "running"
    repository.finish_run(run_id, "completed", "done")
    assert repository.get_run(run_id)["status"] == "completed"


def test_correctness_result_round_trip(repo):
    repository, _ = repo
    meta = RunMeta.start({})
    run_id = repository.insert_run(meta)
    test = load_curated_tests()[0]
    repository.insert_correctness_result(
        run_id, test, "cfg-hash-1", "PASS", message="ok", source_hash="abc"
    )
    rows = repository.results_for_run(run_id)
    assert len(rows) == 1
    assert rows[0]["test_id"] == test.test_id
    assert rows[0]["category"] == "PASS"


def test_compiler_and_config_upsert_is_idempotent(repo):
    repository, db = repo
    identity = CompilerIdentity(
        family="gcc", executable="/usr/bin/g++", version_text="g++ (x) 13.3.0",
        version_major=13, version_minor=3, version_patch=0, target="x86_64-linux-gnu",
    )
    compiler_id_a = repository.upsert_compiler(identity)
    compiler_id_b = repository.upsert_compiler(identity)
    assert compiler_id_a == compiler_id_b
    rows = db.query("SELECT * FROM compiler")
    assert len(rows) == 1
    config_id_a = repository.upsert_compile_config(compiler_id_a, "c++17", "O2", [], "hash-o2")
    config_id_b = repository.upsert_compile_config(compiler_id_a, "c++17", "O2", [], "hash-o2")
    assert config_id_a == config_id_b
    assert len(db.query("SELECT * FROM compile_config")) == 1


def test_benchmark_stats_replace_same_key(repo):
    repository, db = repo
    meta = RunMeta.start({})
    run_id = repository.insert_run(meta)
    stats = BenchmarkStats(5, 0.1, 0.09, 0.11, 0.001)
    repository.insert_benchmark_stat(run_id, "bench_x", "cfg", "v1", stats, 2)
    bigger = BenchmarkStats(10, 0.2, 0.19, 0.21, 0.002)
    repository.insert_benchmark_stat(run_id, "bench_x", "cfg", "v1", bigger, 2)
    rows = repository.benchmark_stats_for_run(run_id)
    assert len(rows) == 1
    assert rows[0]["samples"] == 10


def test_benchmark_samples_batch_insert(repo):
    repository, db = repo
    meta = RunMeta.start({})
    run_id = repository.insert_run(meta)
    samples = [0.10, 0.11, 0.12, 0.10, 0.11]
    repository.insert_benchmark_samples(run_id, "bench_x", "cfg", samples)
    stored = db.query(
        "SELECT sample_index, elapsed_s FROM benchmark_sample "
        "WHERE run_id = ? ORDER BY sample_index", (run_id,)
    )
    assert [row["elapsed_s"] for row in stored] == samples
    # Re-inserting the same indexes updates instead of duplicating.
    repository.insert_benchmark_samples(run_id, "bench_x", "cfg", [0.5] * 5)
    assert len(db.query("SELECT * FROM benchmark_sample WHERE run_id = ?", (run_id,))) == 5


def test_baseline_round_trip_and_host_filtering(repo):
    repository, _ = repo
    meta = RunMeta.start({})
    run_id = repository.insert_run(meta)
    repository.finish_run(run_id, "completed")
    baseline_id = repository.upsert_baseline(
        test_id="bench_x",
        config_hash="cfg",
        benchmark_version="v1",
        stats=BenchmarkStats(5, 0.10, 0.09, 0.11, 0.001),
        source_run_id=run_id,
        host="Linux-host/x86_64",
    )
    assert baseline_id > 0
    hit = repository.latest_baseline("bench_x", "cfg", "v1", "Linux-host/x86_64")
    assert hit is not None
    miss = repository.latest_baseline("bench_x", "cfg", "v1", "Other-host/arm")
    assert miss is None
    # Re-upserting updates in place (UNIQUE test/config/version/host).
    second_id = repository.upsert_baseline(
        test_id="bench_x",
        config_hash="cfg",
        benchmark_version="v1",
        stats=BenchmarkStats(9, 0.12, 0.11, 0.13, 0.001),
        source_run_id=run_id,
        host="Linux-host/x86_64",
    )
    assert second_id == baseline_id


def test_regression_history(repo):
    repository, _ = repo
    meta = RunMeta.start({})
    run_id = repository.insert_run(meta)
    repository.finish_run(run_id, "completed")
    baseline_id = repository.upsert_baseline(
        test_id="bench_x", config_hash="cfg", benchmark_version="v1",
        stats=BenchmarkStats(5, 0.10, 0.09, 0.11, 0.001),
        source_run_id=run_id, host="hostA",
    )
    regression_id = repository.insert_regression(
        run_id=run_id, test_id="bench_x", config_hash="cfg", baseline_id=baseline_id,
        baseline_median=0.10, current_median=0.16, slowdown_pct=60.0,
        verdict="regression", evidence={"explanation": "demo"},
    )
    history = repository.regression_history()
    assert history[0]["id"] == regression_id
    assert history[0]["verdict"] == "regression"
    assert "explanation" in dict(
        __import__("json").loads(history[0]["evidence_json"])
    )


def test_latest_run_id(repo):
    repository, _ = repo
    first = repository.insert_run(RunMeta.start({}))
    second = repository.insert_run(RunMeta.start({}))
    assert repository.latest_run_id() == second
    assert first < second
