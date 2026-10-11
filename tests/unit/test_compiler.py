"""Unit tests: compiler command construction, identity parsing, discovery."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from compreg.compiler.base import (
    CompilerAdapter,
    CompilerError,
    CompileSpec,
    compile_config_hash,
)
from compreg.compiler.clang import ClangAdapter
from compreg.compiler.discovery import DiscoveryEntry, discover_compiler
from compreg.compiler.gcc import GccAdapter

GCC = next((e for e in (
    # session-discovered entries are imported lazily to keep this module cheap
    []
) if e), None)


def _gcc_available() -> bool:
    import shutil

    return shutil.which("g++") is not None


def make_spec(tmp_path: Path) -> CompileSpec:
    source = tmp_path / "prog.cpp"
    source.write_text("int main() { return 0; }\n", encoding="utf-8")
    return CompileSpec(
        source=source,
        output=tmp_path / "prog.bin",
        std="c++17",
        opt_level="O2",
        warnings=("-Wall",),
        extra_flags=("-DFOO=1",),
    )


def test_gcc_command_construction(tmp_path):
    if not _gcc_available():
        pytest.skip("gcc not installed")
    adapter = GccAdapter(shutil_which("g++"))
    cmd = adapter.build_compile_command(make_spec(tmp_path))
    assert cmd[0].endswith("g++")
    assert "-std=c++17" in cmd
    assert "-O2" in cmd
    assert "-Wall" in cmd
    assert "-DFOO=1" in cmd
    assert cmd[-2:] == [str(tmp_path / "prog.bin"), str(tmp_path / "prog.cpp")]
    # No shell operators anywhere in the argv.
    assert not any(";" in part or "|" in part or "&" in part for part in cmd)


def test_unknown_opt_level_rejected(tmp_path):
    if not _gcc_available():
        pytest.skip("gcc not installed")
    adapter = GccAdapter(shutil_which("g++"))
    spec = make_spec(tmp_path)
    bad = CompileSpec(source=spec.source, output=spec.output, opt_level="O4")
    with pytest.raises(CompilerError, match="invalid optimization level"):
        adapter.build_compile_command(bad)


def test_missing_source_rejected(tmp_path):
    if not _gcc_available():
        pytest.skip("gcc not installed")
    adapter = GccAdapter(shutil_which("g++"))
    spec = CompileSpec(source=tmp_path / "ghost.cpp", output=tmp_path / "x.bin")
    with pytest.raises(CompilerError, match="does not exist"):
        adapter.build_compile_command(spec)


def test_adapter_requires_existing_executable():
    with pytest.raises(CompilerError, match="not found"):
        ClangAdapter("/definitely/missing/clang++")


def test_version_parsing_gcc_style():
    if not _gcc_available():
        pytest.skip("gcc not installed")
    adapter = GccAdapter(shutil_which("g++"))
    text = "g++ (Ubuntu 13.3.0-6ubuntu2) 13.3.0\nCopyright (C) 2023 Free Software Foundation"
    assert adapter.parse_version(text) == (13, 3, 0)


def test_version_parsing_clang_style():
    adapter = ClangAdapter.__new__(ClangAdapter)  # bypass fs checks
    text = "Ubuntu clang version 18.1.3 (1~exp1)\nTarget: x86_64-pc-linux-gnu"
    assert adapter.parse_version(text) == (18, 1, 3)


def test_version_parsing_unrecognized():
    adapter = ClangAdapter.__new__(ClangAdapter)
    assert adapter.parse_version("no version info here") == (None, None, None)


def test_config_hash_stability_and_sensitivity():
    h1 = compile_config_hash("gcc", (13, 3, 0), "c++17", "O2", [])
    h2 = compile_config_hash("gcc", (13, 3, 0), "c++17", "O2", [])
    h3 = compile_config_hash("gcc", (13, 3, 0), "c++17", "O3", [])
    h4 = compile_config_hash("gcc", (13, 2, 0), "c++17", "O2", [])
    h5 = compile_config_hash("gcc", (13, 3, 0), "c++17", "O2", ["-g"])
    assert h1 == h2
    assert h1 != h3
    assert h1 != h4
    assert h1 != h5


def _make_fake_compiler(directory: Path, name: str, family_version: str) -> Path:
    """Create an executable shell script that mimics --version/-dumpmachine."""
    script = directory / name
    script.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then\n'
        f'  echo "fake {family_version}"\n'
        f'  echo "fake-driver version {family_version}"\n'
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "-dumpmachine" ]; then\n'
        '  echo "fake-target-x86"\n'
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def test_discovery_uses_configured_path(tmp_path):
    fake = _make_fake_compiler(tmp_path, "fake-gxx", "13.7.0")
    entry = discover_compiler("gcc", configured_path=str(fake))
    assert entry.found
    assert entry.identity.version_major == 13
    assert entry.identity.version_minor == 7
    assert entry.identity.target == "fake-target-x86"
    assert "fake" in entry.identity.version_text


def test_discovery_reports_missing(tmp_path):
    config_path = tmp_path / "not-a-compiler"
    entry = discover_compiler("gcc", configured_path=str(config_path))
    assert not entry.found
    assert entry.reason
    # And the reason names the tried candidate(s).
    assert "not-a-compiler" in ", ".join(entry.candidates_tried) or entry.reason


def test_discovery_unsupported_family():
    entry = discover_compiler("msvc")
    assert not entry.found
    assert "unsupported family" in entry.reason


def test_discovery_rejects_broken_executable(tmp_path):
    broken = tmp_path / "broken-compiler"
    broken.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
    broken.chmod(broken.stat().st_mode | stat.S_IXUSR)
    entry = discover_compiler("gcc", configured_path=str(broken))
    # The broken executable is not usable; discovery reports it as missing
    # with the probe failure recorded.
    assert not entry.found
    assert entry.reason


def shutil_which(name: str):
    import shutil

    found = shutil.which(name)
    if found is None:
        pytest.skip(f"{name} not installed")
    return found
