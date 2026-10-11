"""Typed repository over the SQLite schema: runs, results, baselines, history.

All SQL is parameterized and writes happen inside transactions. Comparison
compatibility (test id + config hash + benchmark version + host) is enforced
at this layer, not just in the CLI.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..models import BenchmarkStats, CompilerIdentity, OracleSpec, RunMeta, TestCase
from ..util import now_iso
from .database import Database

log = logging.getLogger(__name__)


class Repository:
    def __init__(self, database: Database) -> None:
        self.db = database

    # ------------------------------ compilers ----------------------------- #
    def _compiler_lookup(self, identity: CompilerIdentity) -> Optional[Dict[str, Any]]:
        return self.db.query_one(
            """
            SELECT id FROM compiler
            WHERE family = ? AND executable = ? AND version_text = ?
            """,
            (identity.family, identity.executable, identity.version_text),
        )

    def upsert_compiler(self, identity: CompilerIdentity) -> int:
        """Get-or-create a compiler identity row (idempotent).

        INSERT..ON CONFLICT DO UPDATE leaves lastrowid stale on updates, so
        existence is checked explicitly instead.
        """
        existing = self._compiler_lookup(identity)
        if existing:
            return int(existing["id"])
        row_id = self.db.execute_write(
            """
            INSERT INTO compiler(family, executable, version_text, version_major,
                                 version_minor, version_patch, target)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                identity.family,
                identity.executable,
                identity.version_text,
                identity.version_major,
                identity.version_minor,
                identity.version_patch,
                identity.target,
            ),
        )
        return row_id

    def upsert_compile_config(
        self, compiler_id: int, std: str, opt_level: str, extra_flags: Sequence[str], config_hash: str
    ) -> int:
        """Get-or-create a compile configuration row keyed by config_hash."""
        import json as _json

        existing = self.db.query_one(
            "SELECT id FROM compile_config WHERE config_hash = ?", (config_hash,)
        )
        if existing:
            return int(existing["id"])
        return self.db.execute_write(
            """
            INSERT INTO compile_config(compiler_id, std, opt_level, extra_flags, config_hash)
            VALUES(?,?,?,?,?)
            """,
            (compiler_id, std, opt_level, _json.dumps(sorted(extra_flags)), config_hash),
        )

    # ------------------------------ test cases ---------------------------- #
    def upsert_test(self, test: TestCase, source_hash: str) -> int:
        return self.db.execute_write(
            """
            INSERT INTO test_case(test_id, source_path, source_hash, category,
                                  description, oracle_kind, oracle_json, timeout_s,
                                  benchmark_eligible, benchmark_version)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(test_id) DO UPDATE SET
                source_path=excluded.source_path,
                source_hash=excluded.source_hash,
                category=excluded.category,
                description=excluded.description,
                oracle_kind=excluded.oracle_kind,
                oracle_json=excluded.oracle_json,
                timeout_s=excluded.timeout_s,
                benchmark_eligible=excluded.benchmark_eligible,
                benchmark_version=excluded.benchmark_version
            """,
            (
                test.test_id,
                test.source_path,
                source_hash,
                test.category,
                test.description,
                test.oracle.kind.value,
                test.oracle.to_json(),
                test.timeout_s,
                1 if test.benchmark_eligible else 0,
                test.benchmark_version,
            ),
        )

    # -------------------------------- runs -------------------------------- #
    def insert_run(self, meta: RunMeta) -> int:
        run_id = self.db.execute_write(
            """
            INSERT INTO run(started_at, status, host, platform, python_version, tool_json, notes)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                meta.started_at,
                meta.status,
                meta.host,
                meta.platform,
                meta.python_version,
                json.dumps(meta.tool_versions, sort_keys=True),
                meta.notes,
            ),
        )
        meta.run_id = run_id
        return run_id

    def finish_run(self, run_id: int, status: str, notes: str = "") -> None:
        self.db.execute_write(
            "UPDATE run SET status = ?, notes = ? WHERE id = ?", (status, notes, run_id)
        )

    def set_run_tag(self, run_id: int, tag: str) -> None:
        self.db.execute_write("UPDATE run SET tag = ? WHERE id = ?", (tag, run_id))

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        return self.db.query_one("SELECT * FROM run WHERE id = ?", (run_id,))

    def latest_run_id(self) -> Optional[int]:
        row = self.db.query_one("SELECT id FROM run ORDER BY id DESC LIMIT 1")
        return int(row["id"]) if row else None

    # --------------------------- correctness results ---------------------- #
    def insert_correctness_result(
        self,
        run_id: int,
        test: TestCase,
        config_hash: str,
        category: str,
        *,
        expected: str = "",
        actual: str = "",
        exit_code: Optional[int] = None,
        elapsed_s: Optional[float] = None,
        message: str = "",
        artifacts_dir: str = "",
        source_hash: str = "",
    ) -> None:
        self.upsert_test(test, source_hash)
        self.db.execute_write(
            """
            INSERT INTO correctness_result(run_id, test_id, config_hash, category,
                                           expected, actual, exit_code, elapsed_s,
                                           message, artifacts_dir)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id, test_id, config_hash) DO UPDATE SET
                category=excluded.category,
                expected=excluded.expected,
                actual=excluded.actual,
                exit_code=excluded.exit_code,
                elapsed_s=excluded.elapsed_s,
                message=excluded.message,
                artifacts_dir=excluded.artifacts_dir
            """,
            (
                run_id,
                test.test_id,
                config_hash,
                category,
                expected,
                actual,
                exit_code,
                elapsed_s,
                message,
                artifacts_dir,
            ),
        )

    def results_for_run(self, run_id: int) -> List[Dict[str, Any]]:
        return self.db.query(
            """
            SELECT test_id, config_hash, category, message, artifacts_dir, exit_code, elapsed_s
            FROM correctness_result WHERE run_id = ? ORDER BY test_id, config_hash
            """,
            (run_id,),
        )

    def run_summary(self, run_id: int) -> List[Dict[str, Any]]:
        return self.db.query(
            """
            SELECT category, COUNT(*) AS count
            FROM correctness_result WHERE run_id = ? GROUP BY category ORDER BY category
            """,
            (run_id,),
        )

    # ------------------------------ benchmarks ---------------------------- #
    def insert_benchmark_stat(
        self,
        run_id: int,
        test_id: str,
        config_hash: str,
        benchmark_version: str,
        stats: BenchmarkStats,
        warmup: int,
        origin: str = "measured",
    ) -> None:
        self.db.execute_write(
            """
            INSERT INTO benchmark_stat(run_id, test_id, config_hash, benchmark_version,
                                       samples, warmup, median_s, min_s, max_s, mad_s, origin)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id, test_id, config_hash, benchmark_version) DO UPDATE SET
                samples=excluded.samples, warmup=excluded.warmup,
                median_s=excluded.median_s, min_s=excluded.min_s,
                max_s=excluded.max_s, mad_s=excluded.mad_s, origin=excluded.origin
            """,
            (
                run_id, test_id, config_hash, benchmark_version,
                stats.samples, warmup, stats.median_s, stats.min_s, stats.max_s,
                stats.mad_s, origin,
            ),
        )

    def insert_benchmark_samples(
        self,
        run_id: int,
        test_id: str,
        config_hash: str,
        samples: Sequence[float],
        origin: str = "measured",
    ) -> None:
        with self.db.conn:  # one transaction for the whole batch
            for index, elapsed in enumerate(samples):
                self.db.conn.execute(
                    """
                    INSERT INTO benchmark_sample(run_id, test_id, config_hash,
                                                 sample_index, elapsed_s, origin)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(run_id, test_id, config_hash, sample_index) DO UPDATE SET
                        elapsed_s=excluded.elapsed_s, origin=excluded.origin
                    """,
                    (run_id, test_id, config_hash, index, elapsed, origin),
                )

    def benchmark_stat_for_run(
        self, run_id: int, test_id: str, config_hash: str, benchmark_version: str
    ) -> Optional[BenchmarkStats]:
        row = self.db.query_one(
            """
            SELECT samples, median_s, min_s, max_s, mad_s
            FROM benchmark_stat
            WHERE run_id = ? AND test_id = ? AND config_hash = ? AND benchmark_version = ?
            """,
            (run_id, test_id, config_hash, benchmark_version),
        )
        if not row:
            return None
        return BenchmarkStats(
            samples=int(row["samples"]),
            median_s=float(row["median_s"]),
            min_s=float(row["min_s"]),
            max_s=float(row["max_s"]),
            mad_s=float(row["mad_s"]),
        )

    def benchmark_stats_for_run(self, run_id: int) -> List[Dict[str, Any]]:
        return self.db.query(
            """
            SELECT test_id, config_hash, benchmark_version, samples, warmup,
                   median_s, min_s, max_s, mad_s, origin
            FROM benchmark_stat WHERE run_id = ? ORDER BY test_id, config_hash
            """,
            (run_id,),
        )

    # ------------------------------ baselines ----------------------------- #
    def upsert_baseline(
        self,
        *,
        test_id: str,
        config_hash: str,
        benchmark_version: str,
        stats: BenchmarkStats,
        source_run_id: int,
        host: str,
        notes: str = "",
    ) -> int:
        return self.db.execute_write(
            """
            INSERT INTO baseline(created_at, test_id, config_hash, benchmark_version,
                                 median_s, mad_s, samples, source_run_id, host, notes)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(test_id, config_hash, benchmark_version, host) DO UPDATE SET
                created_at=excluded.created_at, median_s=excluded.median_s,
                mad_s=excluded.mad_s, samples=excluded.samples,
                source_run_id=excluded.source_run_id, notes=excluded.notes
            """,
            (
                now_iso(), test_id, config_hash, benchmark_version,
                stats.median_s, stats.mad_s, stats.samples, source_run_id, host, notes,
            ),
        )

    def latest_baseline(
        self, test_id: str, config_hash: str, benchmark_version: str, host: str
    ) -> Optional[Dict[str, Any]]:
        return self.db.query_one(
            """
            SELECT * FROM baseline
            WHERE test_id = ? AND config_hash = ? AND benchmark_version = ? AND host = ?
            ORDER BY id DESC LIMIT 1
            """,
            (test_id, config_hash, benchmark_version, host),
        )

    def latest_matching_baselines(self, run_id: int, require_same_host: bool = True) -> Dict[tuple, Dict[str, Any]]:
        """Map (test_id, config_hash, benchmark_version) -> baseline row
        compatible with the given run."""
        run = self.get_run(run_id)
        host = run["host"] if run else ""
        query = """
            SELECT * FROM baseline
            WHERE test_id = ? AND config_hash = ? AND benchmark_version = ?
              AND (? = 0 OR host = ?)
            ORDER BY id DESC LIMIT 1
        """
        mapping: Dict[tuple, Dict[str, Any]] = {}
        for stat in self.benchmark_stats_for_run(run_id):
            key = (stat["test_id"], stat["config_hash"], stat["benchmark_version"])
            row = self.db.query_one(
                query,
                (stat["test_id"], stat["config_hash"], stat["benchmark_version"],
                 0 if require_same_host else 1, host),
            )
            if row:
                mapping[key] = row
        return mapping

    def list_baselines(self, test_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if test_id:
            return self.db.query(
                "SELECT * FROM baseline WHERE test_id = ? ORDER BY id DESC", (test_id,)
            )
        return self.db.query("SELECT * FROM baseline ORDER BY id DESC")

    # ------------------------------ regressions --------------------------- #
    def insert_regression(
        self,
        *,
        run_id: int,
        test_id: str,
        config_hash: str,
        baseline_id: int,
        baseline_median: float,
        current_median: float,
        slowdown_pct: Optional[float],
        verdict: str,
        evidence: Dict[str, Any],
    ) -> int:
        return self.db.execute_write(
            """
            INSERT INTO regression(detected_at, run_id, test_id, config_hash, baseline_id,
                                   baseline_median_s, current_median_s, slowdown_pct,
                                   verdict, evidence_json)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                now_iso(), run_id, test_id, config_hash, baseline_id,
                baseline_median, current_median, slowdown_pct, verdict,
                json.dumps(evidence, sort_keys=True),
            ),
        )

    def regressions_for_run(self, run_id: int) -> List[Dict[str, Any]]:
        return self.db.query(
            """
            SELECT test_id, config_hash, verdict, baseline_median_s, current_median_s,
                   slowdown_pct, evidence_json, detected_at
            FROM regression WHERE run_id = ? ORDER BY test_id
            """,
            (run_id,),
        )

    def regression_history(self, test_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        if test_id:
            return self.db.query(
                """
                SELECT r.*, run.started_at
                FROM regression r JOIN run ON run.id = r.run_id
                WHERE r.test_id = ? ORDER BY r.id DESC LIMIT ?
                """,
                (test_id, limit),
            )
        return self.db.query(
            """
            SELECT r.*, run.started_at
            FROM regression r JOIN run ON run.id = r.run_id
            ORDER BY r.id DESC LIMIT ?
            """,
            (limit,),
        )

    # ------------------------------ artifacts ----------------------------- #
    def insert_artifact(self, run_id: int, path: str, kind: str) -> None:
        self.db.execute_write(
            "INSERT INTO artifact(run_id, path, kind) VALUES(?,?,?)", (run_id, path, kind)
        )

    # ------------------------------ history ------------------------------- #
    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        runs = self.db.query(
            "SELECT * FROM run ORDER BY id DESC LIMIT ?", (limit,)
        )
        for run in runs:
            run["summary"] = self.run_summary(int(run["id"]))
        return runs
