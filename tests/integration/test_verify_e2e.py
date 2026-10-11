"""Integration tests: differential verification against the live toolchain.

These tests exercise the full compile→execute→classify→persist pipeline with
the installed compiler and are skipped transparently without one.
"""

from __future__ import annotations

import pytest

from conftest import have_gcc, requires_any_compiler
from compreg.config import PROJECT_ROOT
from compreg.compiler.discovery import discover_compiler, discover_compilers
from compreg.corpus.registry import load_ad_hoc_test, load_curated_tests
from compreg.models import ResultCategory
from compreg.verification.differential import verify_tests
from compreg.execution.runner import classify_execution, ProgramRunner, RunRequest


def _gcc_entry():
    return discover_compilers(["gcc"])[0]


@have_gcc
def test_known_correct_program_passes_end_to_end(artifacts_tmp):
    entry = _gcc_entry()
    test = next(t for t in load_curated_tests() if t.test_id == "arithmetic_int_basic")
    outcomes, stats = verify_tests(
        [test], [entry], ["O0", "O2"], artifacts_tmp, "it_pass",
        keep_failure_binaries=True,
    )
    assert stats.total == 2
    assert stats.passed == 2
    assert all(o.category is ResultCategory.PASS for o in outcomes)
    assert outcomes[0].compile_result.ok
    assert outcomes[0].execution_result.returncode == 0
    assert outcomes[0].source_sha256
    assert outcomes[0].artifacts_dir


@have_gcc
def test_deliberate_mismatch_is_detected_and_classified(artifacts_tmp):
    entry = _gcc_entry()
    test = load_ad_hoc_test(
        PROJECT_ROOT / "examples" / "broken_bubble_sort.cpp",
        expected_stdout=(PROJECT_ROOT / "test_corpus" / "sorting" / "sorting_bubble_sort.expected").read_text(encoding="utf-8"),
    )
    outcomes, stats = verify_tests([test], [entry], ["O2"], artifacts_tmp, "it_mismatch")
    assert stats.output_mismatches == 1
    outcome = outcomes[0]
    assert outcome.category is ResultCategory.OUTPUT_MISMATCH
    assert "differ" in outcome.message
    assert outcome.execution_result.returncode == 0  # ran fine, wrong output
    assert outcome.reproduction_run


@have_gcc
def test_compile_error_prevents_execution(artifacts_tmp):
    entry = _gcc_entry()
    test = load_ad_hoc_test(PROJECT_ROOT / "examples" / "compile_error.cpp", expected_stdout="")
    outcomes, stats = verify_tests([test], [entry], ["O2"], artifacts_tmp, "it_compile_error")
    outcome = outcomes[0]
    assert stats.compile_errors == 1
    assert outcome.category is ResultCategory.COMPILE_ERROR
    assert outcome.execution_result is None  # never executed


@have_gcc
def test_timeout_is_enforced_and_classified(artifacts_tmp):
    entry = _gcc_entry()
    test = load_ad_hoc_test(
        PROJECT_ROOT / "examples" / "infinite_loop.cpp",
        expected_stdout="",
        timeout_s=2.0,
    )
    outcomes, stats = verify_tests([test], [entry], ["O2"], artifacts_tmp, "it_timeout")
    outcome = outcomes[0]
    assert stats.timeouts == 1
    assert outcome.category is ResultCategory.TIMEOUT
    assert outcome.execution_result.timed_out


@have_gcc
def test_nonzero_exit_reported(artifacts_tmp):
    entry = _gcc_entry()
    test = load_ad_hoc_test(PROJECT_ROOT / "examples" / "runtime_failure.cpp", expected_stdout="")
    outcomes, stats = verify_tests([test], [entry], ["O2"], artifacts_tmp, "it_nonzero")
    assert stats.nonzero_exits == 1
    assert outcomes[0].category is ResultCategory.NONZERO_EXIT
    assert outcomes[0].execution_result.returncode == 3


@have_gcc
def test_multiple_optimization_levels_consistent(artifacts_tmp):
    entry = _gcc_entry()
    test = next(t for t in load_curated_tests() if t.test_id == "sorting_insertion_sort")
    outcomes, stats = verify_tests(
        [test], [entry], ["O0", "O1", "O2", "O3"], artifacts_tmp, "it_multiopt"
    )
    assert stats.passed == 4
    # Identical normalized output across optimization levels.
    outputs = {o.execution_result.stdout for o in outcomes}
    assert len(outputs) == 1


@have_gcc
def test_missing_compiler_family_produces_skipped_rows_not_silence(artifacts_tmp, tmp_path):
    """Deterministic: inject a compiler path that cannot exist.

    The original version relied on Clang being absent, which broke on runners
    with Clang installed. Constructing a missing entry via a configured path
    works identically on every machine (no environment dependence).
    """
    missing = discover_compiler("gcc", configured_path=str(tmp_path / "no-such-compiler"))
    assert missing.found is False  # precondition: the injected path is unavailable
    test = load_curated_tests()[0]
    outcomes, stats = verify_tests([test], [missing], ["O2"], artifacts_tmp, "it_skip")
    assert stats.total == 1
    assert stats.skipped == 1
    # Not a successful execution and not a failure: purely a reportable skip.
    assert stats.passed == 0
    assert stats.failures() == 0
    assert stats.configs_used == 0
    outcome = outcomes[0]
    assert outcome.category is ResultCategory.SKIPPED
    # The skip reason is preserved and references the injected path.
    assert "no usable gcc" in outcome.message
    assert "no-such-compiler" in outcome.message
    assert outcome.execution_result is None  # nothing was ever run


@have_gcc
def test_cross_configuration_agreement_informational_but_oracle_decides(artifacts_tmp):
    """Agreement between configurations is collected, but a bogus expected
    output must FAIL even though every configuration 'agrees' on it."""
    entry = _gcc_entry()
    test = next(t for t in load_curated_tests() if t.test_id == "arithmetic_int_basic")
    bogus = test
    from dataclasses import replace

    bogus_case = replace(bogus, oracle=replace(bogus.oracle, expected_stdout="wrong expected output\n"))
    outcomes, stats = verify_tests([bogus_case], [entry], ["O0", "O3"], artifacts_tmp, "it_oracle_wins")
    # All configurations produced identical real output, yet the test fails
    # against the (wrong) oracle: the oracle is the decision authority.
    assert stats.passed == 0
    assert stats.output_mismatches == 2


@requires_any_compiler
def test_runner_classifies_live_execution(tmp_path, artifacts_tmp):
    runner = ProgramRunner()
    request = RunRequest(binary="/nonexistent/binary", timeout_s=5)
    result = runner.run(request)
    assert classify_execution(result) == "INFRASTRUCTURE_ERROR"
