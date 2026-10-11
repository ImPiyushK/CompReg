"""SQLite persistence: schema initialization, versioning and connections.

Design notes:
  * Normalized schema; identity/config rows are deduplicated by UNIQUE keys.
  * WAL journaling for light concurrency; foreign keys enforced.
  * schema_meta rows record the schema version for future migrations.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..util import now_iso

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS compiler (
    id            INTEGER PRIMARY KEY,
    family        TEXT NOT NULL,
    executable    TEXT NOT NULL,
    version_text  TEXT NOT NULL,
    version_major INTEGER,
    version_minor INTEGER,
    version_patch INTEGER,
    target        TEXT,
    UNIQUE(family, executable, version_text)
);

CREATE TABLE IF NOT EXISTS compile_config (
    id           INTEGER PRIMARY KEY,
    compiler_id  INTEGER NOT NULL REFERENCES compiler(id),
    std          TEXT NOT NULL,
    opt_level    TEXT NOT NULL,
    extra_flags  TEXT NOT NULL DEFAULT '[]',
    config_hash  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS test_case (
    id                  INTEGER PRIMARY KEY,
    test_id             TEXT NOT NULL UNIQUE,
    source_path         TEXT NOT NULL,
    source_hash         TEXT NOT NULL,
    category            TEXT NOT NULL,
    description         TEXT NOT NULL,
    oracle_kind         TEXT NOT NULL,
    oracle_json         TEXT NOT NULL,
    timeout_s           REAL NOT NULL,
    benchmark_eligible  INTEGER NOT NULL DEFAULT 0,
    benchmark_version   TEXT
);

CREATE TABLE IF NOT EXISTS run (
    id             INTEGER PRIMARY KEY,
    started_at     TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'running',
    host           TEXT NOT NULL,
    platform       TEXT NOT NULL,
    python_version TEXT NOT NULL,
    tool_json      TEXT NOT NULL DEFAULT '{}',
    notes          TEXT,
    tag            TEXT
);

CREATE TABLE IF NOT EXISTS correctness_result (
    id           INTEGER PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES run(id),
    test_id      TEXT NOT NULL,
    config_hash  TEXT NOT NULL,
    category     TEXT NOT NULL,
    expected     TEXT,
    actual       TEXT,
    exit_code    INTEGER,
    elapsed_s    REAL,
    message      TEXT,
    artifacts_dir TEXT NOT NULL DEFAULT '',
    UNIQUE(run_id, test_id, config_hash)
);

CREATE TABLE IF NOT EXISTS benchmark_stat (
    id                INTEGER PRIMARY KEY,
    run_id            INTEGER NOT NULL REFERENCES run(id),
    test_id           TEXT NOT NULL,
    config_hash       TEXT NOT NULL,
    benchmark_version TEXT NOT NULL,
    samples           INTEGER NOT NULL,
    warmup            INTEGER NOT NULL,
    median_s          REAL NOT NULL,
    min_s             REAL NOT NULL,
    max_s             REAL NOT NULL,
    mad_s             REAL NOT NULL,
    origin            TEXT NOT NULL DEFAULT 'measured',
    UNIQUE(run_id, test_id, config_hash, benchmark_version)
);

CREATE TABLE IF NOT EXISTS benchmark_sample (
    id           INTEGER PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES run(id),
    test_id      TEXT NOT NULL,
    config_hash  TEXT NOT NULL,
    sample_index INTEGER NOT NULL,
    elapsed_s    REAL NOT NULL,
    origin       TEXT NOT NULL DEFAULT 'measured'
);

CREATE TABLE IF NOT EXISTS baseline (
    id                INTEGER PRIMARY KEY,
    created_at        TEXT NOT NULL,
    test_id           TEXT NOT NULL,
    config_hash       TEXT NOT NULL,
    benchmark_version TEXT NOT NULL,
    median_s          REAL NOT NULL,
    mad_s             REAL NOT NULL,
    samples           INTEGER NOT NULL,
    source_run_id     INTEGER NOT NULL REFERENCES run(id),
    host              TEXT NOT NULL,
    notes             TEXT,
    UNIQUE(test_id, config_hash, benchmark_version, host)
);

CREATE TABLE IF NOT EXISTS regression (
    id                 INTEGER PRIMARY KEY,
    detected_at        TEXT NOT NULL,
    run_id             INTEGER NOT NULL REFERENCES run(id),
    test_id            TEXT NOT NULL,
    config_hash        TEXT NOT NULL,
    baseline_id        INTEGER NOT NULL REFERENCES baseline(id),
    baseline_median_s  REAL NOT NULL,
    current_median_s   REAL NOT NULL,
    slowdown_pct       REAL,
    verdict            TEXT NOT NULL,
    evidence_json      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS artifact (
    id     INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES run(id),
    path   TEXT NOT NULL,
    kind   TEXT NOT NULL
);
"""

INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_results_run ON correctness_result(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_results_test ON correctness_result(test_id)",
    "CREATE INDEX IF NOT EXISTS idx_bstat_run ON benchmark_stat(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_sample_run ON benchmark_sample(run_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_benchmark_sample "
    "ON benchmark_sample(run_id, test_id, config_hash, sample_index)",
    "CREATE INDEX IF NOT EXISTS idx_regression_run ON regression(test_id, config_hash)",
    "CREATE INDEX IF NOT EXISTS idx_baseline_ctx ON baseline(test_id, config_hash)",
]


class Database:
    """Thin sqlite3 wrapper owning the connection lifetime."""

    def __init__(self, path: str | Path, *, initialize: bool = True) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.conn = sqlite3.connect(str(self.path), timeout=30.0)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error as exc:
            raise RuntimeError(f"could not open database '{self.path}': {exc}") from exc
        if initialize:
            self.init_schema()

    # ------------------------------- lifecycle --------------------------- #
    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:  # pragma: no cover
            pass

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------- schema ------------------------------ #
    def init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(SCHEMA_SQL)
            for statement in INDEX_SQL:
                self.conn.execute(statement)
            self.conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def schema_version(self) -> int:
        try:
            row = self.conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
        except sqlite3.Error:
            return 0
        return int(row["value"]) if row else 0

    # ------------------------------- helpers ----------------------------- #
    def execute_write(self, sql: str, params: tuple) -> int:
        """Run one write inside a transaction; return lastrowid."""
        with self.conn:
            cursor = self.conn.execute(sql, params)
            return int(cursor.lastrowid or 0)

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def query_one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def initialize_database(path: str | Path) -> Database:
    """Open (creating if needed) and initialize the schema."""
    database = Database(path)
    log.info("initialized database %s (schema v%d)", path, database.schema_version())
    return database
