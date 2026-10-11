"""Compiler discovery: find GCC/Clang on configured paths or PATH.

Discovery never assumes a compiler is installed. It records what was tried
and why a family is unavailable so callers can report it explicitly.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .base import CompilerAdapter, CompileSpec, CompilerError
from .clang import ClangAdapter
from .gcc import GccAdapter
from ..models import CompilerIdentity


ADAPTERS: Dict[str, type] = {"gcc": GccAdapter, "clang": ClangAdapter}

STATUS_FOUND = "found"
STATUS_MISSING = "missing"


@dataclass
class DiscoveryEntry:
    family: str
    status: str                      # found | missing
    executable: Optional[str] = None
    identity: Optional[CompilerIdentity] = None
    candidates_tried: List[str] = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def found(self) -> bool:
        return self.status == STATUS_FOUND


def discover_compiler(
    family: str,
    configured_path: Optional[str] = None,
) -> DiscoveryEntry:
    """Discover one compiler family.

    Order: explicitly configured path -> PATH candidates. The chosen
    executable is probed with `--version` (and `-dumpmachine`) to build a
    CompilerIdentity; failures are recorded, not raised.
    """
    if family not in ADAPTERS:
        return DiscoveryEntry(
            family=family,
            status=STATUS_MISSING,
            reason=f"unsupported family '{family}'; supported: {sorted(ADAPTERS)}",
        )
    adapter_cls = ADAPTERS[family]
    candidates = list(adapter_cls.cpp_candidates)
    if configured_path:
        candidates = [configured_path]

    tried: List[str] = []
    for candidate in candidates:
        tried.append(candidate)
        executable = _resolve_executable(candidate)
        if executable is None:
            continue
        try:
            adapter: CompilerAdapter = adapter_cls(executable)
            identity_data = adapter.query_identity()
        except CompilerError as exc:
            # Executable exists but is broken/unusable; keep looking.
            reason = str(exc)
            continue
        return DiscoveryEntry(
            family=family,
            status=STATUS_FOUND,
            executable=executable,
            identity=CompilerIdentity(
                family=identity_data.family,
                executable=identity_data.executable,
                version_text=identity_data.version_text,
                version_major=identity_data.version_major,
                version_minor=identity_data.version_minor,
                version_patch=identity_data.version_patch,
                target=identity_data.target,
                std=identity_data.std,
                warnings=identity_data.warnings,
            ),
        )

    reason = (
        f"no usable {family} C++ driver found; "
        f"tried: {', '.join(tried) if tried else '(none)'}. "
        f"Install {family} or set compiler_paths.{family} in the config file."
    )
    return DiscoveryEntry(family=family, status=STATUS_MISSING, candidates_tried=tried, reason=reason)


def discover_compilers(
    families: List[str],
    configured_paths: Optional[Dict[str, str]] = None,
) -> List[DiscoveryEntry]:
    """Discover every requested compiler family."""
    configured_paths = configured_paths or {}
    return [
        discover_compiler(family, configured_paths.get(family) or None)
        for family in families
    ]


def _resolve_executable(candidate: str) -> Optional[str]:
    """Return an absolute executable path, or None if it cannot be used."""
    if not candidate:
        return None
    if Path(candidate).is_absolute() or Path(candidate).parent != Path("."):
        path = Path(candidate)
        return str(path) if path.is_file() else None
    found = shutil.which(candidate)
    return found


def make_adapter(entry: DiscoveryEntry) -> CompilerAdapter:
    """Build the concrete adapter for a discovered entry."""
    if not entry.found or entry.executable is None:
        raise CompilerError(f"cannot create adapter for unavailable compiler: {entry.reason}")
    return ADAPTERS[entry.family](entry.executable)


def probe_std_support(adapter: CompilerAdapter, std: str, workdir: Path) -> Optional[str]:
    """Verify a compiler accepts `std` by probing a minimal program.

    Returns None on success, or an error string. Used by `compreg doctor`.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    tag = std.replace("+", "p")
    source = workdir / f"probe_{tag}.cpp"
    output = workdir / f"probe_{tag}.bin"
    source.write_text("int main() { return 0; }\n", encoding="utf-8")
    spec = CompileSpec(source=source, output=output, std=std, opt_level="O0", warnings=())
    try:
        completed = subprocess.run(
            adapter.build_compile_command(spec),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"probe compile failed to spawn: {exc}"
    if completed.returncode != 0:
        return f"probe compile failed: {completed.stderr.strip()[:400]}"
    return None
