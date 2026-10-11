"""Isolated compilation with artifact preservation.

Each (test, configuration) pair compiles into its own build directory under
`artifacts/runs/<run_id>/<config>/<test>/`, recording the exact command and
compiler capture. Only trusted corpus sources are ever compiled; the corpus
policy is documented in docs/limitations.md.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from ..compiler.base import CompilerAdapter, CompilerError, CompileSpec
from ..corpus.registry import test_source_abs_path
from ..models import CompileResult, CompilerIdentity, TestCase
from ..util import ensure_dir, format_command, sha256_file, truncate

log = logging.getLogger(__name__)


@dataclass
class BuildEnvironment:
    """Factories used by the build engine; components accept stubs for tests."""

    adapter: CompilerAdapter
    identity: CompilerIdentity
    artifacts_root: Path
    keep_failure_binaries: bool = True

    def build_dir(self, run_id: str, test_id: str) -> Path:
        return ensure_dir(self.artifacts_root / "runs" / run_id / "build" / test_id)


class BuildEngine:
    """Compiles one test under one compiler configuration."""

    def __init__(self, environment: BuildEnvironment) -> None:
        self._env = environment

    def compile_test(
        self,
        run_id: str,
        test: TestCase,
        opt_level: str,
        extra_flags: Optional[Sequence[str]] = None,
        env=None,
    ) -> CompileResult:
        """Run the configured compile; never raises on compile failure.

        Infrastructure problems (e.g. unspawnable executable) are surfaced
        with ok=False plus error_kind, so callers can classify them as
        INFRASTRUCTURE_ERROR rather than a compile defect.
        """
        adapter = self._env.adapter
        identity = self._env.identity
        build_dir = self._env.build_dir(run_id, test.test_id)
        source = test_source_abs_path(test)
        output = build_dir / adapter.default_output_path(build_dir, source)
        flags = list(extra_flags) if extra_flags else list(self._env_extra_flags())

        spec = CompileSpec(
            source=source,
            output=output,
            std=identity.std,
            opt_level=opt_level,
            warnings=list(identity.warnings),
            extra_flags=flags,
        )
        command = adapter.build_compile_command(spec)
        self._write_command_record(build_dir, command)

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300.0,
                check=False,
                env=env,
            )
        except OSError as exc:
            return CompileResult(
                ok=False,
                command=command,
                stdout="",
                stderr="",
                returncode=None,
                elapsed_s=0.0,
                error_kind=f"spawn_failed: {exc}",
            )
        except subprocess.TimeoutExpired:
            return CompileResult(
                ok=False,
                command=command,
                stdout="",
                stderr="(compile exceeded the 300 s internal guard)",
                returncode=None,
                elapsed_s=300.0,
                error_kind="timeout",
            )

        if completed.returncode != 0:
            self._write_log(build_dir, "compile.log", completed.stdout, completed.stderr)
            return CompileResult(
                ok=False,
                command=command,
                stdout=completed.stdout,
                stderr=completed.stderr,
                returncode=completed.returncode,
                elapsed_s=0.0,
                error_kind="compile_failed",
            )

        if not output.exists():
            self._write_log(build_dir, "compile.log", completed.stdout, completed.stderr)
            return CompileResult(
                ok=False,
                command=command,
                stdout=completed.stdout,
                stderr=completed.stderr,
                returncode=completed.returncode,
                elapsed_s=0.0,
                error_kind="missing_output",
            )

        self._write_log(build_dir, "compile.log", completed.stdout, completed.stderr)
        return CompileResult(
            ok=True,
            command=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
            elapsed_s=0.0,
            binary_path=str(output),
        )

    def cleanup_success(self, compile_result: CompileResult) -> None:
        """Delete a successful binary unless failure artifacts are kept."""
        if self._env.keep_failure_binaries:
            return
        if compile_result.binary_path:
            Path(compile_result.binary_path).unlink(missing_ok=True)

    def source_fingerprint(self, test: TestCase) -> str:
        return sha256_file(test_source_abs_path(test))

    # ------------------------------------------------------------------ #
    def _env_extra_flags(self) -> Sequence[str]:
        return self._env.identity.extra_flags

    def _write_command_record(self, build_dir: Path, command: List[str]) -> None:
        (build_dir / "command.txt").write_text(
            format_command(command) + "\n", encoding="utf-8"
        )

    def _write_log(self, build_dir: Path, name: str, stdout: str, stderr: str) -> None:
        try:
            (build_dir / name).write_text(
                f"--- stdout ---\n{truncate(stdout)}\n--- stderr ---\n{truncate(stderr)}\n",
                encoding="utf-8",
            )
        except OSError as exc:  # artifact writing must never break verification
            log.warning("could not write artifact %s: %s", name, exc)
