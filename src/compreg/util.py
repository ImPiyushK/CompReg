"""Small shared utilities: hashing, time, command formatting, logging."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def sha256_text(text: str) -> str:
    """SHA-256 hex digest of a unicode string."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def sha256_file(path: str | Path) -> str:
    """SHA-256 hex digest of a file's contents (streamed)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string with second precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def format_command(argv: Sequence[str]) -> str:
    """Format an argv list as a safe, copy-pasteable command line.

    Uses shlex.join on POSIX and subprocess.list2cmdline on Windows so the
    output can be pasted back into the platform's shell. The result is for
    display/reproduction purposes only; the framework always executes
    argument arrays directly.
    """
    parts = [str(part) for part in argv]
    if os.name == "nt":
        return subprocess.list2cmdline(parts)  # Windows quoting rules
    return shlex.join(parts)


def configure_logging(level: str | int = "INFO") -> None:
    """Configure root logging with a concise structured format."""
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def truncate(text: str, limit: int = 4000) -> str:
    """Truncate long capture output for storage, marking the cut."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text) - limit} more chars]"


def executable_suffix() -> str:
    """Platform-specific suffix appended to built executables."""
    return ".exe" if os.name == "nt" else ""


def which(name: str) -> Optional[str]:
    """PATH lookup that also checks the running interpreter's env.

    pip-installed console scripts (pytest/cmake/ninja) live in `bin` on POSIX
    and in `Scripts` on Windows; `shutil.which` alone misses them when no
    venv is activated.
    """
    found = shutil.which(name)
    if found:
        return found
    import sys

    for prefix in (getattr(sys, "prefix", None), sys.exec_prefix):
        if not prefix:
            continue
        for subdir in ("bin", "Scripts"):  # Scripts: pip wheels on Windows
            candidate = Path(prefix) / subdir / name
            if candidate.is_file() and os.access(str(candidate), os.X_OK):
                return str(candidate)
    return None


def which_all(names: Sequence[str]) -> list[str]:
    """Return every name from `names` that resolves on PATH (in order)."""
    found: list[str] = []
    for name in names:
        path = shutil.which(name)
        if path and path not in found:
            found.append(path)
    return found


def pid_running(pid: int) -> bool:
    """Best-effort check whether a PID exists (used for background jobs)."""
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def python_version_string() -> str:
    return sys.version.split()[0]


def platform_string() -> str:
    """Stable, human-readable platform identifier ('system-release-arch')."""
    import platform

    return f"{platform.system()}-{platform.release()}-{platform.machine()}"


def machine_profile() -> str:
    """Identifier used to judge whether two benchmark runs are comparable."""
    import platform

    return f"{platform.system()}/{platform.machine()}"


def ensure_dir(path: str | Path) -> Path:
    """Create (and return) a directory; callers handle PermissionError etc."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
