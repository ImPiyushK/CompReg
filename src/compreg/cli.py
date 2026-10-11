"""CompReg command-line interface.

Commands (conceptually mapped to the required set):
  doctor          environment/compiler/CMake/SQLite capability report
  list-tests      curated (and optional generated) corpus listing
  generate        deterministically generate bounded test programs
  verify          correctness verification across compiler configurations
  benchmark       repeated timing after a correctness gate
  baseline create persist benchmark baselines from a run
  compare         evaluate a run against baselines (regression verdicts)
  history         stored runs, results, regressions
  minimize        line-level delta-debugging on a failing source
  report          JSON/CSV/terminal report for a run
  triage          write failure-evidence reports for a run
  ctest           run the CTest suite (builds the C++ project first)

Exit codes: 0 verification succeeded; 1 verification failures/regressions;
2 configuration/usage error; 3 infrastructure error.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import __version__
from .config import CompRegConfig, ConfigError, load_config
from .corpus.generator import generate_corpus
from .corpus.registry import CorpusError, load_ad_hoc_test, load_curated_tests, registry_stats
from .compiler.discovery import DiscoveryEntry, discover_compilers, probe_std_support
from .execution import runner as runner_module
from .models import (
    BenchmarkStats,
    CompilerIdentity,
    ResultCategory,
    RunMeta,
    TestCase,
    TestOutcome,
)
from .benchmarking.regression import (
    RegressionPolicy,
    evaluate_regression,
    VERDICT_REGRESSION,
)
from .benchmarking.runner import run_with_stats
from .benchmarking.statistics import compute_stats, slowdown_pct
from .storage.database import Database, initialize_database
from .storage.repository import Repository
from .triage.classifier import collect_for_run
from .verification.differential import verify_tests
from .verification.oracle import evaluate_oracle

logger = logging.getLogger("compreg")

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_CONFIG = 2
EXIT_INFRA = 3


class UsageError(Exception):
    """Bad combination of CLI arguments; maps to exit code 2."""


# ------------------------------------------------------------------ #
# shared context used by all commands
# ------------------------------------------------------------------ #
def _discovery(config: CompRegConfig, workdir: Path) -> Tuple[List[DiscoveryEntry], List[str]]:
    entries = discover_compilers(config.compiler_families, config.compiler_paths)
    notes: List[str] = []
    for entry in entries:
        if entry.found and entry.identity is not None:
            string_probe = probe_std_support(
                _entry_adapter(entry), entry.identity.std or config.std, workdir / "probes"
            )
            if string_probe is not None:
                message = f"{entry.family}: std probe failed: {string_probe}"
                entry.status = "missing"
                entry.reason = message
                notes.append(message)
    return entries, notes


def _entry_adapter(entry: DiscoveryEntry):
    from .compiler.discovery import make_adapter

    return make_adapter(entry)


def _load_tests(
    args: argparse.Namespace,
    *,
    raise_on_missing: bool = True,
    ignore_bench_flags: bool = False,
) -> List[TestCase]:
    curated = load_curated_tests()
    chosen: List[TestCase] = curated
    generated: List[TestCase] = []
    if getattr(args, "generated_manifest", None):
        from .corpus.generator import load_manifest

        generated = load_manifest(args.generated_manifest)
        chosen = curated + generated

    if getattr(args, "tests", None):
        wanted = set(args.tests)
        chosen = [t for t in chosen if t.test_id in wanted]
        missing = wanted - {t.test_id for t in chosen}
        if missing and raise_on_missing:
            raise UsageError(f"unknown test id(s): {', '.join(sorted(missing))}")
    if getattr(args, "category", None):
        chosen = [t for t in chosen if t.category == args.category]
    return chosen


def _available_entries(entries: Sequence[DiscoveryEntry]) -> Tuple[List[DiscoveryEntry], List[str]]:
    usable = [e for e in entries if e.found]
    skipped_notes = [f"{e.family}: {e.reason}" for e in entries if not e.found]
    return usable, skipped_notes


def _open_repo(config: CompRegConfig) -> Tuple[Database, Repository]:
    db = initialize_database(config.resolve_db_path())
    return db, Repository(db)


def _toolchain_versions(config: CompRegConfig, workdir: Path) -> Dict[str, str]:
    versions: Dict[str, str] = {
        "compreg": __version__,
        "python": sys.version.split()[0],
    }
    entries = discover_compilers(config.compiler_families, config.compiler_paths)
    for entry in entries:
        if entry.identity is not None:
            versions[entry.family] = entry.identity.display_name
    return versions


def _run_environment(
    args: argparse.Namespace,
    config: CompRegConfig,
) -> Tuple[CompRegConfig, RunMeta, List[DiscoveryEntry], List[str], str]:
    """Prepare config, run metadata and compilers for verify/benchmark."""
    config = _apply_overrides(config, args)
    workdir = config.resolve_artifacts_dir()
    entries, _ = _discovery(config, workdir)
    run_id_tag = f"r{RunMeta.start({}).started_at.replace(':', '').replace('-', '')[:15]}"
    meta = RunMeta.start(_toolchain_versions(config, workdir))
    return config, meta, entries, _discovery_notes(entries), run_id_tag


def _discovery_notes(entries: Sequence[DiscoveryEntry]) -> List[str]:
    return [f"{e.family}: {e.reason}" for e in entries if not e.found]


def _apply_overrides(config: CompRegConfig, args: argparse.Namespace) -> CompRegConfig:
    """CLI override precedence over the loaded config, with revalidation."""
    if getattr(args, "compilers", None):
        requested = [part.strip() for part in args.compilers.split(",") if part.strip()]
        config.compiler_families = requested
    if getattr(args, "opts", None):
        requested_opts = [part.strip() for part in args.opts.split(",") if part.strip()]
        config.opt_levels = requested_opts
    try:
        if getattr(args, "timeout", None) is not None:
            config.timeout_s = float(args.timeout)
        if getattr(args, "reps", None) is not None:
            config.benchmark_reps = int(args.reps)
        if getattr(args, "warmup", None) is not None:
            config.benchmark_warmup = int(args.warmup)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"invalid numeric override: {exc}") from exc
    try:
        config.validate()
    except ConfigError as exc:
        raise ConfigError(str(exc)) from exc
    return config


def _store_contents(
    config: CompRegConfig,
    repo: Repository,
    meta: RunMeta,
    outcomes: Sequence[TestOutcome],
    *,
    store_db: bool,
    run_id_tag: str,
) -> Optional[int]:
    if not store_db:
        return None
    run_id = repo.insert_run(meta)
    repo.set_run_tag(run_id, run_id_tag)
    compiler_ids: Dict[str, int] = {}
    for outcome in outcomes:
        if outcome.identity and outcome.identity.executable:
            key = f"{outcome.identity.family}|{outcome.identity.executable}|{outcome.identity.version_text}"
            if key not in compiler_ids:
                compiler_ids[key] = repo.upsert_compiler(outcome.identity)
            repo.upsert_compile_config(
                compiler_ids[key],
                config.std,
                outcome.opt_level,
                list(config.extra_flags) + list(outcome.identity.extra_flags),
                outcome.config_hash,
            )
        if outcome.category is ResultCategory.SKIPPED:
            repo.insert_correctness_result(
                run_id,
                outcome.test_case,
                outcome.config_hash,
                outcome.category.value,
                message=outcome.message,
                source_hash=outcome.source_sha256,
            )
            continue
        repo.insert_correctness_result(
            run_id,
            outcome.test_case,
            outcome.config_hash,
            outcome.category.value,
            expected=outcome.test_case.oracle.expected_stdout,
            actual=(outcome.execution_result.stdout if outcome.execution_result else ""),
            exit_code=(outcome.execution_result.returncode if outcome.execution_result else None),
            elapsed_s=(outcome.execution_result.elapsed_s if outcome.execution_result else None),
            message=outcome.message,
            artifacts_dir=outcome.artifacts_dir,
            source_hash=outcome.source_sha256,
        )
    return run_id


# ==================================================================== #
# DOCTOR
# ==================================================================== #
def command_doctor(args: argparse.Namespace) -> int:
    from .reporting.summary import divider

    config = load_config(getattr(args, "config", None))
    if getattr(args, "artifacts", None):
        config.artifacts_dir = Path(args.artifacts)
    if getattr(args, "db", None):
        config.db_path = Path(args.db)
    config = _apply_overrides(config, args)
    workdir = config.resolve_artifacts_dir()

    print(divider("compreg doctor"))
    check: Dict[str, Any] = {
        "compreg_version": __version__,
        "python_version": sys.version.split()[0],
        "platform": runner_module.host_report(),
        "python_ok": sys.version_info >= (3, 11),
        "config": str(Path(config.project_root / "config" / "default.toml")),
    }
    print(f"python: {check['python_version']} (>=3.11 required)")
    print(f"platform: {check['platform']}")

    entries, _ = _discovery(config, workdir)
    for entry in entries:
        if entry.found and entry.identity:
            print(f"compiler {entry.family}: OK  -> {entry.identity.display_name} [{entry.executable}]")
        else:
            print(f"compiler {entry.family}: UNAVAILABLE  ({entry.reason})")
            print(
                f"  hint: install {entry.family} or point compiler_paths.{entry.family} at its "
                "C++ driver in a config file (see docs/installation.md)"
            )

    sqlite_ok = _check_sqlite()
    print(f"sqlite: {'OK ' + sqlite_ok if sqlite_ok else 'UNAVAILABLE'}")

    from .util import which as _which

    ctest_path = _which("ctest")
    cmake_path = _which("cmake")
    print(f"cmake: {'OK ' + cmake_path if cmake_path else 'not found (pip install cmake works)'}")
    print(f"ctest: {'OK ' + ctest_path if ctest_path else 'not found (pip install cmake includes ctest)'}")
    print(f"git:   {'OK ' + (_which('git') or '') if _which('git') else 'git: not found'}")

    stats = registry_stats()
    print(f"corpus: {stats['total']} curated tests ({stats['benchmarks']} benchmarks)")
    try:
        load_curated_tests()
        print("corpus integrity: OK")
    except CorpusError as exc:
        printed_reason = str(exc)
        if "test_corpus" in printed_reason:
            print(
                "corpus integrity: UNAVAILABLE outside a project checkout "
                f"({printed_reason.splitlines()[0]})"
            )
            print(
                "  hint: the CLI corpus/config workflow requires the repository "
                "tree (clone or 'pip install -e .'); see docs/installation.md"
            )
        else:
            print(f"corpus integrity: BROKEN ({printed_reason})")
        return EXIT_INFRA

    for feature in ("python_ok", "platform", "compreg_version"):
        _ = feature
    return EXIT_OK


def _check_sqlite() -> Optional[str]:
    import sqlite3

    try:
        conn = sqlite3.connect(":memory:")
        version = sqlite3.sqlite_version
        conn.execute("select 1")
        conn.close()
        return version
    except sqlite3.Error:
        return None


# ==================================================================== #
# LIST-TESTS
# ==================================================================== #
def command_list_tests(args: argparse.Namespace) -> int:
    try:
        tests = _load_tests(args)
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INFRA
    if getattr(args, "json", False):
        payload = {
            "tests": [
                {
                    "test_id": t.test_id,
                    "category": t.category,
                    "description": t.description,
                    "oracle_kind": t.oracle.kind.value,
                    "timeout_s": t.timeout_s,
                    "benchmark_eligible": t.benchmark_eligible,
                    "source_path": t.source_path,
                }
                for t in tests
            ],
            "stats": registry_stats(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return EXIT_OK
    from .reporting.summary import render_table

    rows = [
        (t.test_id, t.category, str(t.timeout_s) + "s", t.oracle.kind.value, "yes" if t.benchmark_eligible else "-")
        for t in tests
    ]
    print(render_table(("test_id", "category", "timeout", "oracle", "bench"), rows))
    print(f"\ncurated counts: {registry_stats()}")
    return EXIT_OK


# ==================================================================== #
# VERIFY
# ==================================================================== #
def command_verify(args: argparse.Namespace) -> int:
    try:
        config, meta, entries, skipped_notes, run_tag = _run_environment(args, load_config(args.config))
        tests = _load_tests(args)
        if getattr(args, "ad_hoc_source", None):
            tests.append(_build_ad_hoc(args))
    except (ConfigError, UsageError, CorpusError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG if isinstance(exc, (ConfigError, UsageError)) else EXIT_INFRA

    artifacts = config.resolve_artifacts_dir()
    # Hand the FULL discovery list to verify_tests so unavailable families
    # produce explicit SKIPPED rows (never silently dropped).
    outcomes, stats = verify_tests(
        tests=tests,
        entries=list(entries),
        opt_levels=config.opt_levels,
        artifacts_root=artifacts,
        run_id=run_tag,
        std=config.std,
        extra_flags=config.extra_flags,
        default_timeout_s=config.timeout_s,
        keep_failure_binaries=config.keep_failure_binaries,
        env=config.runtime_env(),
    )

    store = not getattr(args, "no_db", False)
    run_id = None
    if store:
        db, repo = _open_repo(config)
        try:
            run_id = _store_contents(config, repo, meta, outcomes, store_db=True, run_id_tag=run_tag)
            repo.finish_run(run_id, "completed" if stats.failures() == 0 else "completed_with_failures",
                            f"verify: passed={stats.passed} failed={stats.failures()} skipped={stats.skipped}")
        finally:
            db.close()

    _write_triage_reports(config, outcomes, run_tag)
    print(_render_verification(run_id, outcomes, skipped_notes))
    return EXIT_FAILURES if stats.failures() > 0 else EXIT_OK


def _build_ad_hoc(args: argparse.Namespace) -> TestCase:
    kind = (getattr(args, "ad_hoc_oracle", None) or "exact")
    expected = args.ad_hoc_expected or ""
    if expected and Path(expected).is_file():
        expected = Path(expected).read_text(encoding="utf-8")
    return load_ad_hoc_test(
        args.ad_hoc_source,
        expected_stdout=expected,
        oracle_kind=kind,  # type: ignore[arg-type]
        tolerance=float(getattr(args, "ad_hoc_tolerance", 1e-9) or 1e-9),
        timeout_s=float(getattr(args, "timeout", None) or 10),
    )


def _render_verification(run_id: Optional[int], outcomes: Sequence[TestOutcome],
                         skipped_notes: Sequence[str]) -> str:
    from .reporting.summary import render_summary

    _ = run_id  # the full summary already prints totals; run id lives in history
    return render_summary(
        "verify results",
        outcomes,
        skipped_notes=skipped_notes,
    )


def _write_triage_reports(config: CompRegConfig, outcomes: Sequence[TestOutcome], run_tag: str) -> List[str]:
    from .triage.classifier import collect_for_run

    directory = config.resolve_artifacts_dir() / "runs" / run_tag / "triage"
    paths = collect_for_run(outcomes, directory)
    return [str(p) for p in paths]


# ==================================================================== #
# BENCHMARK
# ==================================================================== #
def command_benchmark(args: argparse.Namespace) -> int:
    try:
        config, meta, entries, skipped_notes, run_tag = _run_environment(args, load_config(args.config))
        usable, unavailable = _available_entries(entries)
        tests = _load_tests(args, raise_on_missing=False)
        if not usable:
            raise ConfigError(
                "no compilers available for benchmarking: "
                + ("; ".join(unavailable) or "no entries")
            )
    except (ConfigError, UsageError, CorpusError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG if isinstance(exc, (ConfigError, UsageError)) else EXIT_INFRA

    bench_tests = [t for t in tests if t.benchmark_eligible]
    if not bench_tests:
        bench_tests = [t for t in load_curated_tests() if t.benchmark_eligible]
    if getattr(args, "ad_hoc_bench", None):
        expected = args.ad_hoc_expected or ""
        if expected and Path(expected).is_file():
            expected = Path(expected).read_text(encoding="utf-8")
        bench_tests.append(load_ad_hoc_test(
            args.ad_hoc_bench,
            expected_stdout=expected,
            oracle_kind=args.ad_hoc_oracle,
            timeout_s=float(getattr(args, "timeout", None) or 60.0),
            test_id=getattr(args, "ad_hoc_id", None),
        ))
    if getattr(args, "tests", None):
        wanted = set(args.tests)
        bench_tests = [t for t in bench_tests if t.test_id in wanted]
        missing = wanted - {t.test_id for t in bench_tests}
        if missing:
            raise UsageError(f"not benchmark-eligible or unknown: {', '.join(sorted(missing))}")

    db, repo = _open_repo(config)
    run_id = repo.insert_run(meta)
    failure_detected = False
    stat_rows: List[Dict[str, Any]] = []
    try:
        corpus_by_id = {t.test_id: t for t in load_curated_tests()}
        for test in bench_tests:
            correctness_ok = _bench_correctness_gate(
                test, config, run_tag, extra_flags=config.extra_flags
            )
            if not correctness_ok:
                failure_detected = True
                continue
            for entry in usable:
                identity = entry.identity
                for opt_level in config.opt_levels:
                    config_hash = _config_hash(identity, config.std, opt_level, config.extra_flags)
                    binary = _compile_for_bench(
                        config, entry, test, opt_level, run_tag, extra_flags=config.extra_flags
                    )
                    if binary is None:
                        failure_detected = True
                        continue
                    timeout_s = min(test.timeout_s * config.benchmark_timeout_multiplier, 900.0)
                    try:
                        samples, stats = run_with_stats(
                            binary,
                            reps=config.benchmark_reps,
                            warmup=config.benchmark_warmup,
                            timeout_s=timeout_s,
                            executor=runner_module.ProgramRunner(),
                        )
                    except (TimeoutError, RuntimeError) as exc:
                        print(f"  benchmark aborted for {test.test_id}/{opt_level}: {exc}", file=sys.stderr)
                        failure_detected = True
                        continue
                    repo.insert_benchmark_stat(
                        run_id, test.test_id, config_hash, config.benchmark_version,
                        stats, config.benchmark_warmup, origin="measured",
                    )
                    repo.insert_benchmark_samples(
                        run_id, test.test_id, config_hash, samples, origin="measured"
                    )
                    compiler_id = repo.upsert_compiler(identity)
                    repo.upsert_compile_config(
                        compiler_id, config.std, opt_level, list(config.extra_flags), config_hash
                    )
                    stat_rows.append({
                        "test_id": test.test_id,
                        "compiler_family": identity.family,
                        "compiler_version": identity.display_name,
                        "opt_level": opt_level,
                        **stats.to_dict(),
                        "origin": "measured",
                    })
        repo.finish_run(
            run_id,
            "completed" if not failure_detected else "completed_with_failures",
            f"benchmark: tests={len(bench_tests)}",
        )
    finally:
        db.close()

    from .reporting.summary import render_table

    rows = [
        (row["test_id"], row["compiler_family"], row["opt_level"], row["samples"],
         f"{row['median_s']:.4f}", f"{row['min_s']:.4f}", f"{row['max_s']:.4f}", f"{row['mad_s']:.4f}")
        for row in stat_rows
    ]
    print(render_table(("test_id", "compiler", "opt", "n", "median_s", "min_s", "max_s", "mad_s"), rows))
    print(f"\nrun id: {run_id}")
    if skipped_notes:
        print("skipped compiler families:")
        for note in skipped_notes:
            print(f"  - {note}")
    return EXIT_FAILURES if failure_detected else EXIT_OK


def _bench_correctness_gate(
    test: TestCase,
    config: CompRegConfig,
    run_tag: str,
    extra_flags: Sequence[str],
) -> bool:
    """Benchmarks run only after correctness has been validated."""
    from .compiler.discovery import discover_compilers

    entries = [e for e in discover_compilers(config.compiler_families, config.compiler_paths) if e.found]
    outcomes, stats = verify_tests(
        [test], entries, config.opt_levels, config.resolve_artifacts_dir(), run_tag,
        std=config.std, extra_flags=extra_flags,
        keep_failure_binaries=False,
    )
    if stats.failures() == 0:
        return True
    from .reporting.summary import render_summary

    print(render_summary(f"correctness gate failed for {test.test_id}", outcomes))
    return False


def _config_hash(identity: CompilerIdentity, std: str, opt_level: str, extra_flags: Sequence[str]) -> str:
    from .compiler.base import compile_config_hash

    return compile_config_hash(
        identity.family, identity.version_tuple() or (0,), std, opt_level, list(extra_flags)
    )


def _compile_for_bench(
    config: CompRegConfig,
    entry: DiscoveryEntry,
    test: TestCase,
    opt_level: str,
    run_tag: str,
    extra_flags: Sequence[str],
) -> Optional[str]:
    from .corpus.registry import test_source_abs_path
    from .execution.build import BuildEngine, BuildEnvironment

    environment = BuildEnvironment(
        adapter=_entry_adapter(entry),
        identity=entry.identity,
        artifacts_root=config.resolve_artifacts_dir(),
        keep_failure_binaries=False,
    )
    engine = BuildEngine(environment)
    result = engine.compile_test(
        run_id=run_tag,
        test=test,
        opt_level=opt_level,
        extra_flags=list(extra_flags),
        env=config.runtime_env(),
    )
    if not result.ok:
        print(f"  compile failed for {test.test_id}/{opt_level}: {(result.stderr or '').strip()[-300:]}", file=sys.stderr)
        return None
    return result.binary_path


# ==================================================================== #
# BASELINE / COMPARE / HISTORY
# ==================================================================== #
def _resolve_run_ref(config: CompRegConfig, repo: Repository, ref: str) -> int:
    db_repo = repo
    if ref and ref.lower() not in ("latest", "last"):
        try:
            return int(ref)
        except ValueError as exc:
            raise UsageError(f"invalid run reference '{ref}' (use an integer id or 'latest')") from exc
    run_id = db_repo.latest_run_id()
    if run_id is None:
        raise UsageError("no runs stored in the database yet")
    return run_id


def command_baseline_create(args: argparse.Namespace) -> int:
    try:
        config = _apply_overrides(load_config(args.config), args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    db, repo = _open_repo(config)
    try:
        run_id = _resolve_run_ref(config, repo, getattr(args, "run", "latest"))
        stat_rows = repo.benchmark_stats_for_run(run_id)
        if not stat_rows:
            print(f"error: run {run_id} has no benchmark statistics", file=sys.stderr)
            raise UsageError("nothing to baseline")
        host = (repo.get_run(run_id) or {}).get("host", "")
        created = 0
        weak: List[Dict[str, Any]] = []
        for stat in stat_rows:
            stats = BenchmarkStats(
                samples=int(stat["samples"]),
                median_s=float(stat["median_s"]),
                min_s=float(stat["min_s"]),
                max_s=float(stat["max_s"]),
                mad_s=float(stat["mad_s"]),
            )
            policy = RegressionPolicy(
                min_samples=config.benchmark_min_samples,
                rel_threshold=config.regression_rel_threshold,
                abs_threshold_s=config.regression_abs_threshold_s,
                noise_k_mad=config.regression_noise_k_mad,
            )
            if stats.samples < policy.min_samples and not getattr(args, "force", False):
                weak.append(stat)
                continue
            if stats.samples < policy.min_samples and getattr(args, "force", False):
                weak.append({**stat, "n Forced": True})
            baseline_id = repo.upsert_baseline(
                test_id=stat["test_id"],
                config_hash=stat["config_hash"],
                benchmark_version=stat["benchmark_version"],
                stats=stats,
                source_run_id=run_id,
                host=host,
                notes="origin=" + str(stat.get("origin", "measured")),
            )
            created += 1
        print(f"baselines upserted: {created} (source run {run_id})")
        for stat in weak:
            hint = getattr(stat, "get", None) and stat.get("n Forced")
            print(
                f"  note: {stat['test_id']} has {stat['samples']} samples "
                f"(min required {config.benchmark_min_samples}); use --force to accept "
                "a noisy baseline, or benchmark again (recommended)"
            )
        return EXIT_OK
    except (UsageError,) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    finally:
        db.close()


def command_compare(args: argparse.Namespace) -> int:
    try:
        config = _apply_overrides(load_config(args.config), args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    db, repo = _open_repo(config)
    try:
        run_id = _resolve_run_ref(config, repo, getattr(args, "run", "latest"))
        baseline_ref = getattr(args, "baseline", "latest")
        try:
            baseline_run_id = _resolve_run_ref(config, repo, baseline_ref)
        except UsageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_CONFIG

        current_rows = repo.benchmark_stats_for_run(run_id)
        if not current_rows:
            print(f"error: run {run_id} has no benchmark statistics", file=sys.stderr)
            return EXIT_CONFIG

        run_meta = repo.get_run(run_id) or {}
        host = run_meta.get("host", "")
        policy = RegressionPolicy(
            min_samples=config.benchmark_min_samples,
            rel_threshold=config.regression_rel_threshold,
            abs_threshold_s=config.regression_abs_threshold_s,
            noise_k_mad=config.regression_noise_k_mad,
        )

        verdicts = []
        regression_rows = []
        current_run_rows = {r["test_id"] + "|" + r["config_hash"]: r for r in current_rows}
        baseline_by_key: Dict[tuple, Dict[str, Any]] = {}
        for row in current_run_rows.values():
            key = (row["test_id"], row["config_hash"])
            candidates = repo.db.query(
                """
                SELECT * FROM baseline
                WHERE test_id = ? AND config_hash = ? AND benchmark_version = ?
                  AND (? = 0 OR host = ?)
                ORDER BY id DESC LIMIT 1
                """,
                (key[0], key[1], row["benchmark_version"],
                 0 if config.require_same_host else 1, host),
            )
            if not candidates and not config.require_same_host:
                continue
            if not candidates:
                # no baseline for this context yet
                baseline_by_key[key] = {}
                continue
            baseline_by_key[key] = candidates[0]

        for key, baseline in baseline_by_key.items():
            test_id, config_hash = key
            current = BenchmarkStats(
                samples=int(current_run_rows[test_id + "|" + config_hash]["samples"]),
                median_s=float(current_run_rows[test_id + "|" + config_hash]["median_s"]),
                min_s=float(current_run_rows[test_id + "|" + config_hash]["min_s"]),
                max_s=float(current_run_rows[test_id + "|" + config_hash]["max_s"]),
                mad_s=float(current_run_rows[test_id + "|" + config_hash]["mad_s"]),
            )
            if not baseline:
                verdicts.append(("no_baseline", test_id, config_hash, None, None, None,
                                 "no compatible baseline exists yet (create one first)"))
                continue
            baseline_stats = BenchmarkStats(
                samples=int(baseline["samples"]),
                median_s=float(baseline["median_s"]),
                min_s=0.0,
                max_s=0.0,
                mad_s=float(baseline["mad_s"]),
            )
            verdict = evaluate_regression(
                policy=policy,
                test_id=test_id,
                config_hash=config_hash,
                baseline=baseline_stats,
                current=current,
            )
            repo.insert_regression(
                run_id=run_id,
                test_id=test_id,
                config_hash=config_hash,
                baseline_id=int(baseline["id"]),
                baseline_median=baseline_stats.median_s,
                current_median=current.median_s,
                slowdown_pct=verdict.slowdown_pct,
                verdict=verdict.verdict,
                evidence={
                    "verdict_explanation": verdict.explanation,
                    "policy": {
                        "rel_threshold": policy.rel_threshold,
                        "abs_threshold_s": policy.abs_threshold_s,
                        "noise_k_mad": policy.noise_k_mad,
                        "min_samples": policy.min_samples,
                    },
                    "host": host,
                    "": "",
                },
            )
            verdicts.append(
                (
                    verdict.verdict,
                    test_id,
                    config_hash[:8],
                    verdict.baseline_median_s if baseline_stats.median_s else None,
                    verdict.current_median_s,
                    verdict.slowdown_pct if verdict.slowdown_pct is not None else None,
                    verdict.explanation if verdict.verdict in (VERDICT_REGRESSION, "insufficient_samples", "incompatible") else "",
                )
            )
            if verdict.verdict == VERDICT_REGRESSION:
                regression_rows.append(verdict)

        from .reporting.summary import render_table

        rows = [
            (
                v[0],
                v[1],
                str(v[2]),
                "-" if v[3] is None else f"{v[3]:.4f}",
                "-" if v[4] is None else f"{v[4]:.4f}",
                "-" if v[5] is None else f"{v[5]:+.1f}%",
                v[6] or "",
            )
            for v in verdicts
        ]
        print(render_table(("verdict", "test_id", "config", "baseline_s", "current_s", "slowdown", "note"), rows))
        print(f"\nrun compared: {run_id}")
        return EXIT_FAILURES if regression_rows else EXIT_OK
    finally:
        db.close()


def command_history(args: argparse.Namespace) -> int:
    try:
        config = _apply_overrides(load_config(args.config), args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    db, repo = _open_repo(config)
    try:
        if getattr(args, "test", None):
            history = repo.regression_history(test_id=args.test, limit=args.limit)
            from .reporting.summary import render_table

            rows = [
                (
                    h["id"], h["run_id"], h["test_id"], h["verdict"],
                    f"{h['baseline_median_s']:.4f}", f"{h['current_median_s']:.4f}",
                    "-" if h["slowdown_pct"] is None else f"{h['slowdown_pct']:+.1f}%",
                    h["started_at"],
                )
                for h in history
            ]
            print(render_table(("id", "run", "test_id", "verdict", "base_s", "curr_s", "slowdown", "date"), rows))
            print(f"\n{len(history)} regression record(s) for '{args.test}'")
            return EXIT_OK

        runs = repo.list_runs(limit=args.limit)
        from .reporting.summary import render_table

        rows = []
        for run in runs:
            summary_map = {entry["category"]: entry["count"] for entry in run["summary"]}
            rows.append(
                (
                    run["id"],
                    run["started_at"],
                    run["status"],
                    summary_map.get("PASS", 0),
                    sum(count for category, count in summary_map.items()
                        if category not in ("PASS", "SKIPPED")),
                    summary_map.get("SKIPPED", 0),
                )
            )
        print(render_table(("run", "started", "status", "pass", "fail", "skip"), rows))
        print(
            f"\nlatest run id: {repo.latest_run_id()}; use `compreg report --run <id>` for detail"
        )
        return EXIT_OK
    finally:
        db.close()


# ==================================================================== #
# MINIMIZE
# ==================================================================== #
def command_minimize(args: argparse.Namespace) -> int:
    try:
        config = _apply_overrides(load_config(args.config), args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    source = Path(args.source)
    if not source.is_file():
        print(f"error: source not found: {source}", file=sys.stderr)
        return EXIT_CONFIG
    xin = config
    from .compiler.discovery import discover_compilers
    from .compiler.base import CompileSpec, CompilerError

    entries = [e for e in discover_compilers(config.compiler_families, config.compiler_paths) if e.found]
    if not entries:
        print("error: no compilers available for minimization", file=sys.stderr)
        return EXIT_CONFIG
    entry = entries[0]
    if getattr(args, "compiler", None):
        matched = [e for e in entries if e.family == args.compiler]
        if not matched:
            print(f"error: compiler '{args.compiler}' unavailable (have: {[e.family for e in entries]})", file=sys.stderr)
            return EXIT_CONFIG
        entry = matched[0]
    import subprocess as _sp

    original_text = source.read_text(encoding="utf-8")

    def compile_and_check(candidate_text: str):
        """Compile+run a candidate; returns object with .compiled/.stdout."""
        from dataclasses import dataclass as _dc

        @_dc
        class Result:
            compiled: bool
            stdout: str

        tmpdir = config.resolve_artifacts_dir() / "minimize" / f"m{abs(hash(candidate_text)) % 10**10}"
        tmpdir.mkdir(parents=True, exist_ok=True)
        src = tmpdir / "candidate.cpp"
        out = tmpdir / "candidate.bin"
        src.write_text(candidate_text, encoding="utf-8")
        try:
            adapter = _entry_adapter(entry)
            cmd = adapter.build_compile_command(
                CompileSpec(source=src, output=out, std=config.std,
                            opt_level=args.opt, warnings=list(entry.identity.warnings),
                            extra_flags=list(config.extra_flags))
            )
        except CompilerError:
            return Result(compiled=False, stdout="")
        try:
            compile_result = _sp.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        except (OSError, _sp.SubprocessError):
            return Result(compiled=False, stdout="")
        if compile_result.returncode != 0:
            return Result(compiled=False, stdout="")
        try:
            run_result = _sp.run([str(out)], capture_output=True, text=True,
                                 timeout=max(1.0, float(getattr(args, "timeout", None) or config.timeout_s)), check=False)
        except (OSError, _sp.SubprocessError):
            return Result(compiled=True, stdout="")
        return Result(compiled=True, stdout=run_result.stdout)

    expected_text = args.expected
    if expected_text and Path(expected_text).is_file():
        expected_text = Path(expected_text).read_text(encoding="utf-8")
    oracle_kind = (args.oracle or "exact") if hasattr(args, "oracle") else "exact"

    def oracle_check(stdout_text: str) -> bool:
        from .models import OracleSpec
        from .verification.oracle import evaluate_oracle

        ok, _ = evaluate_oracle(
            OracleSpec(kind=oracle_kind, expected_stdout=expected_text, tolerance=1e-6),
            stdout_text,
            0,
        )
        return ok

    from .triage.minimizer import minimize_lines

    # Determine the original failure signature: compile-error vs runtime mismatch.
    original_result = compile_and_check(original_text)
    original_failing_via_compile = not original_result.compiled
    if not original_failing_via_compile:
        # Standard reduction criterion: reproduce the identical failing output
        # (an empty/absent output that merely fails the oracle is NOT the same
        # failure and must not be accepted).
        original_failing_stdout = original_result.stdout

    def predicate(candidate_text: str) -> bool:
        outcome = compile_and_check(candidate_text)
        if original_failing_via_compile:
            return not outcome.compiled
        if not outcome.compiled:
            return False
        if original_failing_stdout:
            return outcome.stdout == original_failing_stdout
        return not oracle_check(outcome.stdout)

    result = minimize_lines(
        original_text,
        predicate,
        max_evaluations=int(getattr(args, "max_evaluations", 300)),
    )
    out_dir = config.resolve_artifacts_dir() / "minimize" / source.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    minimized_path = out_dir / "minimized.cpp"
    testimonial = out_dir
    minimized_path.write_text(result.minimized, encoding="utf-8")
    (out_dir / "original-preserved.cpp").write_text(original_text, encoding="utf-8")

    print(f"minimization of {source}")
    print(f"  original lines: {len(original_text.splitlines())}")
    print(f"  minimized lines: {len(result.minimized.splitlines()) if result.minimized else 0}")
    print(f"  minimized bytes: {result.reduced}")
    print(f"  evaluations:      {result.evaluations}")
    print(f"  minimized source: {minimized_path}")
    print(f"  original preserved: {out_dir / 'original-preserved.cpp'}")
    print(f"  compiler used:    {entry.identity.display_name} -{args.opt}")
    print(
        "  limitation: line-granular reduction; predicates are behavioral "
        "(compile/run), not syntactic"
    )
    return EXIT_OK


# ------------------------------------------------------------------- #
# neglected: glue used above
# ------------------------------------------------------------------- #
def _open_repo_checked(config: CompRegConfig):
    return _open_repo(config)


# ==================================================================== #
# REPORT / TRIAGE / GENERATE / CTEST
# ==================================================================== #
def command_report(args: argparse.Namespace) -> int:
    try:
        config = _apply_overrides(load_config(args.config), args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    db, repo = _open_repo(config)
    try:
        run_id = _resolve_run_ref(config, repo, getattr(args, "run", "latest"))
        run_meta = repo.get_run(run_id)
        if run_meta is None:
            print(f"error: run {run_id} not found", file=sys.stderr)
            return EXIT_CONFIG
        results = repo.results_for_run(run_id)
        stats_rows = repo.benchmark_stats_for_run(run_id)
        regressions = repo.regressions_for_run(run_id)
        hash_labels = {
            row["config_hash"]: row
            for row in repo.db.query(
                """
                SELECT cc.config_hash, cc.opt_level, cc.std, c.family, c.version_text
                FROM compile_config cc JOIN compiler c ON c.id = cc.compiler_id
                """
            )
        }
    finally:
        db.close()

    for row in results:
        label = hash_labels.get(row["config_hash"])
        if label:
            row["opt_level"] = label["opt_level"]
            row["compiler_family"] = label["family"]
            row["compiler_version"] = label["version_text"]
    for row in stats_rows:
        label = hash_labels.get(row["config_hash"])
        if label:
            row["opt_level"] = label["opt_level"]
            row["compiler_family"] = label["family"]
            row["compiler_version"] = label["version_text"]

    from .reporting.csv_report import BENCHMARK_COLUMNS, benchmark_rows, write_csv
    from .reporting.csv_report import (
        CORRECTNESS_COLUMNS,
        correctness_rows,
    )

    correctness = correctness_rows([]) if False else None
    rows_for_csv = _db_rows_to_outcomes_like(results)
    csv_rows = correctness_rows(rows_for_csv) if rows_for_csv else []
    metadata = {
        "run_id": run_id,
        "started_at": run_meta["started_at"],
        "host": run_meta["host"],
        "platform": run_meta["platform"],
        "python_version": run_meta["python_version"],
        "tool_versions": json.loads(run_meta["tool_json"]),
        "notes": run_meta["notes"],
        "artifacts": [
            {"results_dir": str(config.resolve_artifacts_dir() / "runs")},
        ],
    }

    from .reporting.json_report import build_json_report, write_json
    from .benchmarking.regression import RegressionVerdict

    verdicts = [
        RegressionVerdict(
            test_id=r["test_id"],
            config_hash=r["config_hash"],
            compatible=True,
            incompatibility_reason=None,
            baseline_median_s=r["baseline_median_s"],
            current_median_s=r["current_median_s"],
            baseline_samples=None,
            current_samples=None,
            slowdown_pct=r["slowdown_pct"],
            verdict=r["verdict"],
            explanation=json.loads(r["evidence_json"]).get("verdict_explanation", ""),
        )
        for r in regressions
    ]
    report = build_json_report(rows_for_csv, verdicts, metadata)

    out_prefix = Path(args.out) if getattr(args, "out", None) else config.resolve_artifacts_dir() / f"report_run{run_id}"
    json_path = write_json(report, str(out_prefix) + ".json")
    csv_path = write_csv(csv_rows, str(out_prefix) + "_correctness.csv", CORRECTNESS_COLUMNS)
    bench_csv_path = write_csv(benchmark_rows(stats_rows), str(out_prefix) + "_benchmarks.csv", BENCHMARK_COLUMNS)

    from .reporting.summary import render_summary, render_bt_table

    print(render_summary(f"report for run {run_id}", rows_for_csv, benchmark_lines=[
        render_bt_table(stats_rows),
    ], regression_lines=[
        f"{r['verdict']}: {r['test_id']} ({r['config_hash'][:8]}) "
        + (f"slowdown {r['slowdown_pct']:+.1f}%" if r["slowdown_pct"] is not None else "")
        for r in regressions
    ]))
    print("exports:")
    print(f"  json: {json_path}")
    print(f"  csv:  {csv_path}")
    print(f"  csv:  {bench_csv_path}")
    has_failures = any(r["category"] not in ("PASS", "SKIPPED") for r in results) or \
        any(r["verdict"] == VERDICT_REGRESSION for r in regressions)
    return EXIT_FAILURES if has_failures else EXIT_OK


def _db_rows_to_outcomes_like(results: Sequence[Dict[str, Any]]) -> List[TestOutcome]:
    """Reconstruct lightweight outcome records from DB rows for reports.

    The DB rows carry the decision and metadata needed for reporting; the
    compile/run captures stay in the artifacts directory.
    """
    from .models import TestCase, CompilerIdentity

    outcomes: List[TestOutcome] = []
    for row in results:
        case = TestCase(
            test_id=row["test_id"],
            source_path="(from database)",
            category=row.get("category", "stored"),
            description="",
            oracle=_noop_oracle(row),
        )
        identity = CompilerIdentity(
            family=row.get("compiler_family") or "stored",
            executable="",
            version_text=row.get("compiler_version") or "",
        )
        outcome = TestOutcome(
            test_case=case,
            identity=identity,
            opt_level=row.get("opt_level") or "?",
            config_hash=row["config_hash"],
            category=ResultCategory(row["category"]),
            message=row.get("message") or "",
            artifacts_dir=row.get("artifacts_dir") or "",
        )
        outcomes.append(outcome)
    return outcomes


def _noop_oracle(row: Dict[str, Any]):
    from .models import OracleKind, OracleSpec

    return OracleSpec(kind=OracleKind.EXACT, expected_stdout=row.get("expected") or "")


def command_triage(args: argparse.Namespace) -> int:
    try:
        config = _apply_overrides(load_config(args.config), args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    db, repo = _open_repo(config)
    try:
        run_id = _resolve_run_ref(config, repo, getattr(args, "run", "latest"))
        run_meta = repo.get_run(run_id)
        results = [r for r in repo.results_for_run(run_id)
                   if r["category"] not in ("PASS", "SKIPPED")]
        run_tag = run_meta.get("tag") if run_meta else None
    finally:
        db.close()

    if not results:
        print(f"no failures recorded for run {run_id}")
        return EXIT_OK

    printed = 0
    # Preferred: full live triage artifacts written during the original run.
    if run_tag:
        tag_dir = config.resolve_artifacts_dir() / "runs" / run_tag / "triage"
        if tag_dir.is_dir():
            for path in sorted(tag_dir.glob("triage_*.json")):
                print(f"triage report: {path}")
                printed += 1

    if not printed:
        # Fallback: reconstruct the recorded essentials from the DB rows and
        # note explicitly which context is NOT available without artifacts.
        from .models import TestCase, CompilerIdentity, ResultCategory, TestOutcome
        from .triage.classifier import build_triage, write_triage_report

        out_dir = config.resolve_artifacts_dir() / "runs" / f"run{run_id}" / "triage"
        for row in results:
            test = TestCase(
                test_id=row["test_id"], source_path="(stored)", category="stored",
                description="", oracle=_noop_oracle(row),
            )
            outcome = TestOutcome(
                test_case=test,
                identity=CompilerIdentity(family="?", executable="", version_text=""),
                opt_level=row["config_hash"][:6],
                config_hash=row["config_hash"],
                category=ResultCategory(row["category"]),
                message=row["message"] or "",
                artifacts_dir=row.get("artifacts_dir") or "",
            )
            item = build_triage(outcome)
            path = write_triage_report(item, out_dir / f"triage_{test.test_id}.json")
            print(f"triage report (reconstructed): {path}")
            print("  note: full compile/run captures live in the run artifacts "
                  "directory; reproduce from there when available")
            printed += 1
    return EXIT_FAILURES


def command_generate(args: argparse.Namespace) -> int:
    try:
        config = _apply_overrides(load_config(args.config), args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    output_dir = Path(args.out) if getattr(args, "out", None) else config.resolve_artifacts_dir()
    from .corpus.generator import generate_corpus

    try:
        manifest = generate_corpus(args.count, args.seed, output_dir)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    link = output_dir / "generated" / "manifest.json"
    print(f"generated {len(manifest)} program(s) with seed {args.seed} in {output_dir / 'generated'}")
    print(f"manifest: {link}")
    print("verify them with: compreg verify --include-generated " + str(link))
    for generated in manifest:
        print(f"  - {generated.test_case.test_id}")
    return EXIT_OK


def command_ctest(args: argparse.Namespace) -> int:
    """"ctest" command: configure+build+run the native C++/CTest suite."""
    try:
        config = load_config(args.config)
        config = _apply_overrides(config, args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    build_dir = Path(getattr(args, "build_dir", None) or config.resolve_artifacts_dir() / "ctest-build")
    build_dir.parent.mkdir(parents=True, exist_ok=True)
    from .util import which as _which

    cmake_path = _which("cmake")
    ctest_path = _which("ctest")
    if cmake_path is None or ctest_path is None:
        print("error: cmake/ctest not found (PATH or interpreter env)", file=sys.stderr)
        print("hint: pip install cmake works, or install the OS package", file=sys.stderr)
        return EXIT_INFRA
    ninja_path = _which("ninja")
    configure_args = [
        cmake_path, "-S", str(config.project_root), "-B", str(build_dir),
        "-DCMAKE_BUILD_TYPE=Release",
        # Make CMake prefer the interpreter that runs compreg (venv-friendly),
        # so the pytest-backed CTest tests register when pytest is importable.
        f"-DPython3_EXECUTABLE={sys.executable}",
        f"-DPYTHON_EXECUTABLE={sys.executable}",
    ]
    if ninja_path is not None:
        configure_args += ["-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={ninja_path}"]
    configure = _sp_run(configure_args)
    if configure.returncode != 0:
        print(configure.stdout[-2000:]); print(configure.stderr[-2000:], file=sys.stderr)
        return EXIT_INFRA
    build = _sp_run([cmake_path, "--build", str(build_dir), "-j"], timeout=600)
    if build.returncode != 0:
        print(build.stdout[-2000:]); print(build.stderr[-2000:], file=sys.stderr)
        return EXIT_INFRA
    run = _sp_run([ctest_path, "--output-on-failure"], cwd=str(build_dir), timeout=600)
    print(run.stdout)
    return EXIT_OK if run.returncode == 0 else EXIT_FAILURES


def _sp_run(argv: List[str], cwd: Optional[str] = None, timeout: float = 300.0):
    import subprocess

    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


# ==================================================================== #
# PARSER + MAIN
# ==================================================================== #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="compreg",
        description="CPU-only compiler verification and regression-analysis framework "
        "(differential testing, benchmarking, history, triage).",
    )
    parser.add_argument("--version", action="version", version=f"compreg {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help="path to a TOML config file (layered over config/default.toml)")
    common.add_argument("--compilers", help="comma-separated compiler families (overrides config)")
    common.add_argument("--opts", help="comma-separated optimization levels, e.g. O0,O2 (overrides config)")
    common.add_argument("--timeout", type=float, help="per-test execution timeout in seconds (overrides config)")
    common.add_argument("--artifacts", help="artifacts directory override")
    common.add_argument("--db", help="SQLite database path override")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", parents=[common], help="environment and capability report")
    p.set_defaults(func=command_doctor)

    p = sub.add_parser("list-tests", parents=[common], help="list the curated test corpus")
    p.add_argument("--category", help="filter by category")
    p.add_argument("--include-generated", dest="generated_manifest", help="manifest.json from `compreg generate`")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=command_list_tests)

    p = sub.add_parser("generate", parents=[common], help="deterministically generate bounded test programs")
    p.add_argument("--count", type=int, default=6)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", help="output directory (default artifacts/)")
    p.set_defaults(func=command_generate)

    p = sub.add_parser("verify", parents=[common], help="run correctness verification")
    p.add_argument("--tests", nargs="*", help="test ids (default: all curated)")
    p.add_argument("--category", help="filter by category")
    p.add_argument("--include-generated", dest="generated_manifest", help="manifest.json from `compreg generate`")
    p.add_argument("--no-db", action="store_true", help="do not persist results")
    p.add_argument("--ad-hoc-source", help="extra source file (trusted demo/CI fixtures only)")
    p.add_argument("--ad-hoc-expected", help="expected stdout text or path to an .expected file")
    p.add_argument("--ad-hoc-oracle", choices=["exact", "float-list", "exit-code"], default="exact")
    p.set_defaults(func=command_verify)

    p = sub.add_parser("benchmark", parents=[common], help="repeatable wall-clock benchmarking")
    p.add_argument("--tests", nargs="*", help="benchmark test ids (default: all bench-eligible)")
    p.add_argument("--reps", type=int, help="measured repetitions (overrides config)")
    p.add_argument("--warmup", type=int, help="discarded warm-up runs (overrides config)")
    p.add_argument("--no-db", action="store_true", help="do not persist results")
    p.add_argument("--ad-hoc-bench", help="benchmark a custom source file (trusted demo fixtures only)")
    p.add_argument("--ad-hoc-id", help="stable test id for the custom benchmark (required for baseline flows)")
    p.add_argument("--ad-hoc-expected", help="expected stdout for the custom benchmark")
    p.add_argument("--ad-hoc-oracle", choices=["exact", "float-list"], default="exact")
    p.set_defaults(func=command_benchmark)

    p = sub.add_parser("baseline", parents=[common], help="baselines subcommand")
    bsub = p.add_subparsers(dest="baseline_command", required=True)
    bp = bsub.add_parser("create", parents=[common], help="create baselines from a stored run")
    bp.add_argument("--run", default="latest", help="run id or 'latest'")
    bp.add_argument("--force", action="store_true", help="accept baselines with fewer than min samples")
    bp.set_defaults(func=command_baseline_create)

    p = sub.add_parser("compare", parents=[common], help="evaluate run benchmarks against baselines")
    p.add_argument("--run", default="latest", help="run id or 'latest'")
    p.add_argument("--baseline", default="latest", help="baseline provider run id or 'latest'")
    p.set_defaults(func=command_compare)

    p = sub.add_parser("history", parents=[common], help="historical runs and regressions")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--test", help="show regression history for one test id")
    p.set_defaults(func=command_history)

    p = sub.add_parser("minimize", parents=[common], help="delta-debug a failing source program")
    p.add_argument("--source", required=True, help="failing source file")
    p.add_argument("--expected", required=True, help="expected stdout text or .expected file path")
    p.add_argument("--oracle", choices=["exact", "float-list"], default="exact")
    p.add_argument("--compiler", help="compiler family to reproduce with")
    p.add_argument("--opt", default="O2", help="optimization level for reproduction guards")
    p.add_argument("--max-evaluations", type=int, default=300)
    p.set_defaults(func=command_minimize)

    p = sub.add_parser("report", parents=[common], help="export a stored run as JSON/CSV + summary")
    p.add_argument("--run", default="latest", help="run id or 'latest'")
    p.add_argument("--out", help="output prefix for <prefix>.json/.csv exports")
    p.set_defaults(func=command_report)

    p = sub.add_parser("triage", parents=[common], help="failure-evidence reports for a run")
    p.add_argument("--run", default="latest")
    p.set_defaults(func=command_triage)

    p = sub.add_parser("ctest", parents=[common], help="configure/build/run the CTest suite")
    p.add_argument("--build-dir", help="CMake build directory (default artifacts/ctest-build)")
    p.set_defaults(func=command_ctest)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname).1s %(name)s: %(message)s",
    )
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except (UsageError, ConfigError, CorpusError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except Exception as exc:  # infrastructure failures must be visible
        logger.exception("infrastructure failure")
        print(f"infrastructure error: {exc}", file=sys.stderr)
        return EXIT_INFRA


