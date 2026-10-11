"""Differential verification across compilers and optimization levels.

Decision policy (documented):
  Each (test, compiler, opt level) outcome is decided ONLY by that test's
  oracle. Cross-configuration agreement is collected and reported as
  evidence, never as the pass criterion.

Skipped configurations (e.g. requested compiler not installed) are recorded
with SKIPPED status and the reason; they are never silently dropped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..compiler.base import CompilerError
from ..compiler.discovery import DiscoveryEntry, make_adapter
from ..execution.build import BuildEngine, BuildEnvironment
from ..execution.runner import ProgramRunner, RunRequest, classify_execution
from ..models import (
    CompilerIdentity,
    ResultCategory,
    TestOutcome,
    TestCase,
)
from ..verification.oracle import evaluate_oracle
from ..util import format_command, sha256_text

log = logging.getLogger(__name__)


@dataclass
class VerifiedRunStats:
    total: int = 0
    passed: int = 0
    compile_errors: int = 0
    output_mismatches: int = 0
    nonzero_exits: int = 0
    timeouts: int = 0
    execution_errors: int = 0
    infrastructure_errors: int = 0
    skipped: int = 0
    configs_used: int = 0

    def failures(self) -> int:
        return (
            self.compile_errors + self.output_mismatches + self.nonzero_exits +
            self.timeouts + self.execution_errors + self.infrastructure_errors
        )


def _empty_descriptor_stats() -> VerifiedRunStats:
    return VerifiedRunStats()


def verify_tests(
    tests: Sequence[TestCase],
    entries: Sequence[DiscoveryEntry],
    opt_levels: Sequence[str],
    artifacts_root: Path,
    run_id: str,
    std: str = "c++17",
    extra_flags: Sequence[str] = (),
    default_timeout_s: float = 10.0,
    keep_failure_binaries: bool = True,
    env=None,
) -> tuple[List[TestOutcome], VerifiedRunStats]:
    """Run every (test x available compiler x opt level) combination.

    Returns outcomes in deterministic order (test -> family -> opt level).
    Unavailable compiler families yield SKIPPED outcomes with reasons.
    """
    runner = ProgramRunner()
    outcomes: List[TestOutcome] = []
    stats = _empty_descriptor_stats()
    used_configs: set[str] = set()

    for entry in entries:
        if entry.found and entry.identity is not None:
            adapter = _safe_make_adapter(entry)
            environment: Optional[BuildEnvironment] = None
            if adapter is not None:
                environment = BuildEnvironment(
                    adapter=adapter,
                    identity=entry.identity,
                    artifacts_root=artifacts_root,
                    keep_failure_binaries=keep_failure_binaries,
                )
        else:
            adapter = None
            environment = None

        for test in tests:
            timeout_s = test.timeout_s if test.timeout_s else default_timeout_s
            for opt_level in opt_levels:
                outcome = _verify_one(
                    runner=runner,
                    environment=environment,
                    identity=entry.identity,
                    found=entry.found,
                    missing_reason=entry.reason,
                    test=test,
                    opt_level=opt_level,
                    std=std,
                    extra_flags=extra_flags,
                    timeout_s=timeout_s,
                    stats_source=(artifacts_root, run_id, keep_failure_binaries),
                    env=env,
                )
                outcomes.append(outcome)
                _collect_stats(outcome, stats)
                if outcome.category is not ResultCategory.SKIPPED:
                    used_configs.add(f"{entry.family}|{opt_level}")
                if outcome.is_failure:
                    log.warning(
                        "failure: %s/%s/%s -> %s (%s)",
                        test.test_id, entry.family, opt_level, outcome.category.name, outcome.message,
                    )

    stats.total = len(outcomes)
    stats.passed = sum(1 for o in outcomes if o.category is ResultCategory.PASS)
    stats.skipped = sum(1 for o in outcomes if o.category is ResultCategory.SKIPPED)
    stats.configs_used = len(used_configs)
    return outcomes, stats


def _safe_make_adapter(entry: DiscoveryEntry):
    try:
        return make_adapter(entry)
    except CompilerError as exc:
        log.warning("adapter construction failed for %s: %s", entry.family, exc)
        return None


def _verify_one(
    runner: ProgramRunner,
    environment: Optional[BuildEnvironment],
    identity: Optional[CompilerIdentity],
    found: bool,
    missing_reason: Optional[str],
    test: TestCase,
    opt_level: str,
    std: str,
    extra_flags: Sequence[str],
    timeout_s: float,
    stats_source: tuple,
    env=None,
) -> TestOutcome:
    artifacts_root, run_id, keep_binaries = stats_source
    config_hash = sha256_text(
        "|".join(
            [
                identity.family if identity else "unavailable",
                ".".join(str(p) for p in identity.version_tuple()) if identity else "",
                std,
                opt_level,
                ",".join(sorted(extra_flags)),
            ]
        )
    )[:16]

    def skipped(category: ResultCategory, reason: str) -> TestOutcome:
        return TestOutcome(
            test_case=test,
            identity=identity or CompilerIdentity(family="unavailable", executable="", version_text=""),
            opt_level=opt_level,
            config_hash=config_hash,
            category=category,
            message=reason,
        )

    if not found or environment is None or identity is None:
        return skipped(
            ResultCategory.SKIPPED,
            missing_reason or f"compiler unavailable for test '{test.test_id}'",
        )

    build_engine = BuildEngine(environment)
    outcome_dir = artifacts_root / "runs" / run_id / "results" / \
        f"{test.test_id}_{identity.family}_{opt_level}"

    try:
        compile_result = build_engine.compile_test(
            run_id=run_id,
            test=test,
            opt_level=opt_level,
            extra_flags=extra_flags,
            env=env,
        )
    except CompilerError as exc:
        return _infra_failure(test, identity, opt_level, config_hash, f"build setup failed: {exc}")

    source_sha256 = build_engine.source_fingerprint(test)

    if not compile_result.ok:
        if compile_result.error_kind and compile_result.error_kind.startswith("spawn_failed"):
            category = ResultCategory.INFRASTRUCTURE_ERROR
            message = compile_result.error_kind
        else:
            category = ResultCategory.COMPILE_ERROR
            error_lines = (compile_result.stderr or "").strip().splitlines()
            diagnostic = next(
                (line for line in error_lines if "error" in line.lower()), None
            )
            message = diagnostic or (error_lines[-1] if error_lines else "compilation failed")
        runner.persist_artifacts(outcome_dir, compile_result, None)
        return _build_outcome(
            test, identity, opt_level, config_hash, category, message,
            compile_result=compile_result, execution_result=None,
            artifacts_dir=str(outcome_dir), source_sha256=source_sha256,
        )

    request = RunRequest(
        binary=compile_result.binary_path or "",
        timeout_s=timeout_s,
        program_args=(),
        env=env,
    )

    try:
        execution_result = runner.run(request)
    except Exception as exc:  # defensive: runner is designed not to raise
        return _build_outcome(
            test, identity, opt_level, config_hash,
            ResultCategory.INFRASTRUCTURE_ERROR, f"unexpected runner failure: {exc}",
            compile_result=compile_result, execution_result=None,
            artifacts_dir=str(outcome_dir), source_sha256=source_sha256,
        )

    execution_category = classify_execution(execution_result)

    if execution_category == ResultCategory.PASS.value:
        ok, explanation = evaluate_oracle(
            test.oracle, execution_result.stdout, execution_result.returncode
        )
        category = ResultCategory.PASS if ok else ResultCategory.OUTPUT_MISMATCH
        message = explanation
    elif execution_category == ResultCategory.NONZERO_EXIT.value:
        # exit-code oracles legitimately expect nonzero exits
        expected_code = test.oracle.expected_exit_code
        if test.oracle.kind.value == "exit-code" and execution_result.returncode == expected_code:
            ok, explanation = evaluate_oracle(
                test.oracle, execution_result.stdout, execution_result.returncode
            )
            category = ResultCategory.PASS if ok else ResultCategory.OUTPUT_MISMATCH
            message = explanation
        else:
            category = ResultCategory.NONZERO_EXIT
            message = f"exit code {execution_result.returncode} (expected 0 or oracle-passing)"
    else:
        category = ResultCategory(execution_category)
        message = {
            "TIMEOUT": f"timed out after {timeout_s} s",
            "EXECUTION_ERROR": "binary terminated without a usable exit code",
            "INFRASTRUCTURE_ERROR": execution_result.error_kind or "execution infrastructure failure",
        }.get(category.name, category.name)

    runner.persist_artifacts(outcome_dir, compile_result, execution_result)

    if category is ResultCategory.PASS:
        build_engine.cleanup_success(compile_result)

    return _build_outcome(
        test, identity, opt_level, config_hash, category, message,
        compile_result=compile_result,
        execution_result=execution_result,
        expected=test.oracle.expected_stdout,
        artifacts_dir=str(outcome_dir),
        source_sha256=source_sha256,
    )


def _build_outcome(
    test: TestCase,
    identity: CompilerIdentity,
    opt_level: str,
    config_hash: str,
    category: ResultCategory,
    message: str,
    compile_result=None,
    execution_result=None,
    expected: str = "",
    artifacts_dir: str = "",
    source_sha256: str = "",
) -> TestOutcome:
    compile_cmd = list(compile_result.command) if compile_result else []
    run_cmd = list(execution_result.command) if execution_result else []
    return TestOutcome(
        test_case=test,
        identity=identity,
        opt_level=opt_level,
        config_hash=config_hash,
        category=category,
        message=message,
        compile_result=compile_result,
        execution_result=execution_result,
        source_sha256=source_sha256,
        artifacts_dir=artifacts_dir,
        reproduction_compile=compile_cmd,
        reproduction_run=run_cmd,
    )


def _infra_failure(
    test: TestCase,
    identity: Optional[CompilerIdentity],
    opt_level: str,
    config_hash: str,
    message: str,
) -> TestOutcome:
    return TestOutcome(
        test_case=test,
        identity=identity
        or CompilerIdentity(family="unavailable", executable="", version_text=""),
        opt_level=opt_level,
        config_hash=config_hash,
        category=ResultCategory.INFRASTRUCTURE_ERROR,
        message=message,
    )


def _collect_stats(outcome: TestOutcome, stats: VerifiedRunStats) -> None:
    mapping = {
        ResultCategory.COMPILE_ERROR: "compile_errors",
        ResultCategory.OUTPUT_MISMATCH: "output_mismatches",
        ResultCategory.NONZERO_EXIT: "nonzero_exits",
        ResultCategory.TIMEOUT: "timeouts",
        ResultCategory.EXECUTION_ERROR: "execution_errors",
        ResultCategory.INFRASTRUCTURE_ERROR: "infrastructure_errors",
    }
    attr = mapping.get(outcome.category)
    if attr:
        setattr(stats, attr, getattr(stats, attr) + 1)


def reproduction_command_line(outcome: TestOutcome) -> str:
    """Human-readable repro strings for reports (copies, not executed).

    For outcomes reconstructed from the database (whose argv lists were not
    persisted), the artifact directory's command.txt / run_command.txt files
    provide the same information; they are read when present.
    """
    import os
    from pathlib import Path

    parts = [format_command(outcome.reproduction_compile)] if outcome.reproduction_compile else []
    if outcome.reproduction_run:
        parts.append(format_command(outcome.reproduction_run))
    if outcome.is_failure and not parts:
        artifacts_dir = Path(outcome.artifacts_dir) if outcome.artifacts_dir else None
        if artifacts_dir and artifacts_dir.is_dir():
            for name in ("command.txt", "run_command.txt"):
                candidate = artifacts_dir / name
                if candidate.is_file():
                    first = candidate.read_text(encoding="utf-8").strip().splitlines()
                    if first:
                        parts.append(first[0])
    return " && ".join(parts)
