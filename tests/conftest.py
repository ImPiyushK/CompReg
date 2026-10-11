"""Shared pytest fixtures and skips.

Integration tests require a real C++ compiler and are marked
`requires_compiler`; they skip transparently when none is installed (this is
a deliberate, reported capability boundary rather than a silent drop).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

# Make the src layout importable even without `pip install -e .`.
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from compreg.compiler.discovery import discover_compilers  # noqa: E402

GXX = shutil.which("g++") or shutil.which("g++-14") or shutil.which("g++-13")
CLANGXX = shutil.which("clang++") or shutil.which("clang++-18") or shutil.which("clang++-17")

# One shared discovery result for the test session.
DISCOVERY = discover_compilers(["gcc", "clang"])


def _found(family: str) -> bool:
    return any(e.found and e.family == family for e in DISCOVERY)


have_gcc = pytest.mark.skipif(
    not _found("gcc"),
    reason="GCC not installed",
)
have_clang = pytest.mark.skipif(
    not _found("clang"),
    reason="Clang not installed (optional capability)",
)
requires_any_compiler = pytest.mark.skipif(
    not (_found("gcc") or _found("clang")),
    reason="no C++ compiler installed",
)


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture()
def artifacts_tmp(tmp_path: Path) -> Path:
    """Isolated artifacts directory for a test."""
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    return artifacts
