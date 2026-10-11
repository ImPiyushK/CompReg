"""Common compiler adapter interface.

Adapters translate a CompileSpec into an argv list (never a shell string),
report compiler identity metadata, and stay behind an ABC so additional
compiler families can be added later.
"""

from __future__ import annotations

import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, List, Optional, Sequence, Tuple

from ..util import executable_suffix, sha256_text


class CompilerError(Exception):
    """Raised when a compiler adapter cannot be constructed or probed."""


@dataclass(frozen=True)
class CompileSpec:
    """One compile request (source -> binary)."""

    source: Path
    output: Path
    std: str = "c++17"
    opt_level: str = "O2"          # "O0".."O3", stored without dash
    warnings: Sequence[str] = ("-Wall", "-Wextra")
    extra_flags: Sequence[str] = ()
    language: str = "c++"

    def flags_normalized(self) -> Tuple[str, ...]:
        return tuple(str(flag) for flag in self.extra_flags)


class CompilerAdapter(ABC):
    """Abstract adapter for a compiler family.

    Concrete adapters declare `family` and the command names to search for,
    and inherit the GNU-style command construction shared by GCC/Clang.
    """

    family: ClassVar[str] = "abstract"
    #: Preferred C++ driver names, in priority order.
    cpp_candidates: ClassVar[Tuple[str, ...]] = ()
    #: Primary pattern: "<name> version X.Y.Z".
    version_regex: ClassVar[str] = r"version\s+(\d+)\.(\d+)(?:\.(\d+))?"
    #: Fallback for GCC-style first lines: "g++ (distro 13.3.0-6ubuntu2) 13.3.0".
    version_fallback_regex: ClassVar[str] = r"(?<![\d.])(\d+)\.(\d+)(?:\.(\d+))?"

    def __init__(self, executable: str) -> None:
        self.executable = executable
        # Sanity check without requiring compilation.
        if not Path(executable).exists() and not _on_path(executable):
            raise CompilerError(f"configured {self.family} executable not found: {executable}")

    # ------------------------------------------------------------------ #
    # metadata
    # ------------------------------------------------------------------ #
    @abstractmethod
    def query_identity(self) -> "CompilerIdentityData":
        """Query version/target information by invoking the compiler."""

    # ------------------------------------------------------------------ #
    # command construction
    # ------------------------------------------------------------------ #
    def build_compile_command(self, spec: CompileSpec) -> List[str]:
        """Build the full compile argv for a spec.

        Uses argument arrays only; callers must not embed this in a shell.
        """
        if spec.opt_level not in ("O0", "O1", "O2", "O3"):
            raise CompilerError(f"invalid optimization level '{spec.opt_level}'")
        if not spec.source.exists():
            raise CompilerError(f"source file does not exist: {spec.source}")

        cmd: List[str] = [self.executable]
        if spec.std:
            cmd.append(f"-std={spec.std}")
        cmd.append(f"-{spec.opt_level}")
        cmd.extend(spec.warnings)
        cmd.extend(self.extra_default_flags())
        cmd.extend(spec.extra_flags)
        cmd.extend(["-o", str(spec.output)])
        cmd.append(str(spec.source))
        return cmd

    def extra_default_flags(self) -> Tuple[str, ...]:
        """Family-specific flags added to every compile (may be empty)."""
        return ()

    # ------------------------------------------------------------------ #
    # probing helpers shared by subclasses
    # ------------------------------------------------------------------ #
    def capture_version_text(self) -> str:
        try:
            completed = subprocess.run(
                [self.executable, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CompilerError(f"failed to run '{self.executable} --version': {exc}") from exc
        if completed.returncode != 0 and not completed.stdout.strip():
            raise CompilerError(
                f"'{self.executable} --version' failed with exit code {completed.returncode}"
            )
        # Keep the first banner line only: it contains the version; trailing
        # copyright lines would pollute display/database fields.
        text = completed.stdout.strip() or completed.stderr.strip()
        return text.splitlines()[0]

    def query_target(self) -> Optional[str]:
        """Return `-dumpmachine` output when the driver supports it."""
        try:
            completed = subprocess.run(
                [self.executable, "-dumpmachine"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip().splitlines()[0]
        return None

    def parse_version(self, version_text: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        match = re.search(self.version_regex, version_text)
        if not match:
            # First line only for the fallback, to avoid matching stray
            # numbers in later banner output.
            first_line = version_text.splitlines()[0] if version_text else ""
            match = re.search(self.version_fallback_regex, first_line)
        if not match:
            return (None, None, None)
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3)) if match.group(3) is not None else None
        return (major, minor, patch)

    def default_output_path(self, build_dir: Path, source: Path) -> Path:
        return build_dir / (source.stem + executable_suffix())


@dataclass
class CompilerIdentityData:
    """Plain metadata returned by `query_identity`."""

    family: str
    executable: str
    version_text: str
    version_major: Optional[int]
    version_minor: Optional[int]
    version_patch: Optional[int]
    target: Optional[str]
    std: str = "c++17"
    extra_flags: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ("-Wall", "-Wextra")

    @property
    def display_name(self) -> str:
        version = ".".join(
            str(part)
            for part in (self.version_major, self.version_minor, self.version_patch)
            if part is not None
        )
        base = f"{self.family} {version}" if version else self.family
        return f"{base} ({self.target})" if self.target else base

    @property
    def version_tuple(self) -> Tuple[int, ...]:
        return tuple(  # type: ignore[return-value]
            part
            for part in (self.version_major, self.version_minor, self.version_patch)
            if part is not None
        )


def _on_path(executable: str) -> bool:
    from shutil import which

    return which(executable) is not None


def compile_config_hash(
    identity_family: str,
    version_tuple: Sequence[Optional[int]],
    std: str,
    opt_level: str,
    extra_flags: Sequence[str],
) -> str:
    """Stable hash identifying one compiler/configuration combination.

    Two results are only comparable when built by the same compiler version
    with the same standard, optimization level and extra flags.
    """
    parts = [
        identity_family,
        ".".join(str(part) for part in version_tuple),
        std,
        opt_level,
        ",".join(sorted(str(flag) for flag in extra_flags)),
    ]
    return sha256_text("|".join(parts))[:16]
