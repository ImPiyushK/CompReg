"""Binary execution with timeouts, capture and platform-safe argument arrays.

Security note (documented, honest): subprocess execution enforces a time
limit and captures output, but it is NOT a security sandbox. The corpus
policy is that test sources are trusted or reviewed; see docs/limitations.md.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..util import ensure_dir, format_command, platform_string, truncate

log = logging.getLogger(__name__)


@dataclass
class RunRequest:
    binary: str
    timeout_s: float
    program_args: Sequence[str] = ()
    env: Optional[Dict[str, str]] = None
    cwd: Optional[str] = None


class ProgramRunner:
    """Executes compiled binaries and captures their observable behavior."""

    def run(self, request: RunRequest):
        """Return (ExecutionResult). Always resolves; never raises."""
        from ..models import ExecutionResult

        argv: List[str] = [request.binary, *request.program_args]
        start_wall = _perf_now()
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=request.timeout_s,
                check=False,
                env=request.env,
                cwd=request.cwd,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = _perf_now() - start_wall
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            return ExecutionResult(
                ok=False,
                command=argv,
                stdout=stdout,
                stderr=stderr,
                returncode=None,
                elapsed_s=elapsed,
                timed_out=True,
                error_kind="timeout",
            )
        except OSError as exc:
            return ExecutionResult(
                ok=False,
                command=argv,
                stdout="",
                stderr="",
                returncode=None,
                elapsed_s=0.0,
                error_kind=f"spawn_failed: {exc}",
            )
        elapsed = _perf_now() - start_wall
        crashed = completed.returncode != 0
        return ExecutionResult(
            ok=not crashed,
            command=argv,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
            elapsed_s=elapsed,
            timed_out=False,
        )

    # ------------------------------------------------------------------ #
    def persist_artifacts(
        self,
        outcome_dir: Path,
        compile_result,
        execution_result,
    ) -> Path:
        """Write run.log/run-stderr.log/command records for diagnostics."""
        artifacts = ensure_dir(outcome_dir)
        if execution_result is not None:
            (artifacts / "run_command.txt").write_text(
                format_command(execution_result.command) + "\n", encoding="utf-8"
            )
            payload = [
                f"--- stdout ---\n{truncate(execution_result.stdout)}",
                f"--- stderr ---\n{truncate(execution_result.stderr)}",
                f"exit code: {execution_result.returncode}",
                f"elapsed seconds: {execution_result.elapsed_s:.6f}",
                f"timed out: {execution_result.timed_out}",
            ]
            (artifacts / "run.log").write_text("\n".join(payload) + "\n", encoding="utf-8")
        if compile_result is not None and getattr(compile_result, "stderr", None):
            (artifacts / "compile-capture.txt").write_text(
                compile_result.stderr or "", encoding="utf-8"
            )
        return artifacts


def _perf_now() -> float:
    import time

    return time.perf_counter()


def classify_execution(execution_result) -> str:
    """Map an ExecutionResult onto a failure category (string value)."""
    from ..models import ResultCategory

    if execution_result is None:
        return ResultCategory.INFRASTRUCTURE_ERROR.value
    if execution_result.error_kind == "timeout" or execution_result.timed_out:
        return ResultCategory.TIMEOUT.value
    if execution_result.error_kind and execution_result.error_kind.startswith("spawn_failed"):
        return ResultCategory.INFRASTRUCTURE_ERROR.value
    if execution_result.returncode is None:
        return ResultCategory.EXECUTION_ERROR.value
    if execution_result.returncode != 0:
        return ResultCategory.NONZERO_EXIT.value
    return ResultCategory.PASS.value  # subject to oracle evaluation upstream


def host_report() -> str:
    """One-line host description used in artifacts (text only)."""
    return platform_string()
