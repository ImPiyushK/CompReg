"""Integration tests: CTest execution, generated programs, and minimization.

Marked slow where builds/compiles dominate; all remain bounded.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import have_gcc, requires_any_compiler

from compreg.config import PROJECT_ROOT
from compreg.cli import command_ctest
from compreg.util import which as _which
from compreg.compiler.discovery import discover_compilers
from compreg.corpus.generator import generate_corpus, load_manifest
from compreg.verification.differential import verify_tests
from compreg.models import ResultCategory


@requires_any_compiler
@pytest.mark.slow
def test_ctest_suite_actually_executes(artifacts_tmp, tmp_path):
    """Build the C++ project and run its CTest tests through the CLI command."""
    if _which("cmake") is None or _which("ctest") is None:
        pytest.skip("cmake/ctest not available (pip install cmake provides them)")

    class Args:
        config = None
        artifacts = None
        db = None
        compilers = None
        opts = None
        timeout = None
        reps = None
        warmup = None
        build_dir = str(tmp_path / "ctest-build")

    rc = command_ctest(Args())
    assert rc == 0


@have_gcc
@pytest.mark.slow
def test_generated_programs_compile_and_pass(tmp_path, artifacts_tmp):
    manifest = generate_corpus(3, 2024, tmp_path / "gen")
    tests = load_manifest(tmp_path / "gen" / "generated" / "manifest.json")
    assert len(tests) == 3
    entry = discover_compilers(["gcc"])[0]
    outcomes, stats = verify_tests(tests, [entry], ["O2"], artifacts_tmp, "it_generated")
    assert stats.passed == 3
    assert all(o.category is ResultCategory.PASS for o in outcomes)


@have_gcc
@pytest.mark.slow
def test_minimize_preserves_failure_and_reduces(artifacts_tmp, tmp_path):
    """Minimize a small failing fixture; the failing output must be preserved."""
    entry = discover_compilers(["gcc"])[0]

    fixture = tmp_path / "fixture.cpp"
    fixture.write_text(
        "// minimized-fixture\n"
        "#include <cstdio>\n"
        "\n"
        "static int helper1(int x) { return x * 3 + 1; }\n"
        "static int helper2(int x) { return x + 11; }\n"
        "\n"
        "int main() {\n"
        "    int value = helper1(14);            // 43\n"
        "    int wrong = helper2(0) + helper1(0); // 12 -> expected 99\n"
        "    std::printf(\"%d\\n\", value + wrong);\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    # helper1(14)=43; helper2(0)=11; helper1(0)=1 -> 43+12 = 55. Expected 99:
    # deliberately contradictory, so the program always fails this oracle.

    from compreg.triage.minimizer import minimize_lines

    original_text = fixture.read_text(encoding="utf-8")

    import tempfile
    import subprocess as sp

    eval_counter = {"n": 0}
    original_stdout = None

    def compile_run(text: str) -> tuple[bool, str]:
        work = tmp_path / "mini" / str(eval_counter["n"])
        eval_counter["n"] += 1
        work.mkdir(parents=True, exist_ok=True)
        src = work / "c.cpp"
        src.write_text(text, encoding="utf-8")
        out = work / "c.bin"
        cmd = [entry.executable, "-std=c++17", "-O2", "-o", str(out), str(src)]
        compiled = sp.run(cmd, capture_output=True, timeout=60, check=False).returncode == 0
        if not compiled:
            return False, ""
        run = sp.run([str(out)], capture_output=True, text=True, timeout=10, check=False)
        return True, run.stdout

    ok, failing_stdout = compile_run(original_text)
    assert ok
    assert "55" in failing_stdout
    original_stdout = failing_stdout

    def predicate(candidate: str) -> bool:
        compiled, stdout = compile_run(candidate)
        return compiled and stdout == original_stdout

    result = minimize_lines(original_text, predicate, max_evaluations=150)
    assert result.reduced, "small fixture must reduce"
    assert result.minimized != original_text
    # The candidate still produces the identical failing output.
    compiled, stdout = compile_run(result.minimized)
    assert compiled and stdout == original_stdout
    assert result.evaluations <= 151
