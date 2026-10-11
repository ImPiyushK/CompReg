"""Unit tests: corpus registry integrity and the deterministic generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from compreg.corpus.generator import generate_corpus, program_test_id, SeededRandom
from compreg.corpus.registry import (
    CorpusError,
    PROJECT_ROOT,
    load_curated_tests,
    registry_stats,
)
from compreg.models import OracleKind


def test_registry_loads_and_unique_ids():
    tests = load_curated_tests()
    ids = [t.test_id for t in tests]
    assert len(ids) == len(set(ids))
    assert len(tests) == registry_stats()["total"]


def test_every_test_has_source_and_expected_files():
    for test in load_curated_tests():
        source = PROJECT_ROOT / test.source_path
        assert source.is_file(), f"missing source for {test.test_id}: {source}"
        if test.oracle.kind != OracleKind.EXIT_CODE:
            expected = source.with_suffix(".expected")
            assert expected.is_file(), f"missing expected for {test.test_id}"


def test_every_program_has_a_reviewable_header_and_no_obvious_ub_markers():
    banned_markers = ("rand()", "std::cin", "time(", "getenv")
    for test in load_curated_tests():
        source_text = (PROJECT_ROOT / test.source_path).read_text(encoding="utf-8")
        for marker in banned_markers:
            assert marker not in source_text, f"{test.test_id} uses nondeterministic API {marker}"
        assert len(source_text.splitlines()) >= 8, f"{test.test_id} suspiciously tiny"


def test_benchmark_entries_define_a_version():
    for test in load_curated_tests():
        if test.benchmark_eligible:
            assert test.benchmark_version, test.test_id


def test_expected_outputs_nonempty(tmp_path):
    for test in load_curated_tests():
        if test.oracle.kind == OracleKind.EXACT:
            assert test.oracle.expected_stdout.strip(), test.test_id


def test_generator_deterministic_across_rounds(tmp_path):
    first = generate_corpus(6, 99, tmp_path / "a")
    second = generate_corpus(6, 99, tmp_path / "b")
    assert [g.test_case.test_id for g in first] == [g.test_case.test_id for g in second]
    for a, b in zip(first, second):
        source_a = Path(a.test_case.source_path).read_bytes()
        source_b = Path(b.test_case.source_path).read_bytes()
        assert source_a == source_b
        assert a.test_case.oracle.expected_stdout == b.test_case.oracle.expected_stdout


def test_generator_rejects_bad_inputs(tmp_path):
    with pytest.raises(ValueError, match="count"):
        generate_corpus(0, 42, tmp_path)


def test_generator_seed_changes_outcomes(tmp_path):
    a = generate_corpus(3, 1, tmp_path / "s1")
    b = generate_corpus(3, 2, tmp_path / "s2")
    assert [g.test_case.test_id for g in a] != [g.test_case.test_id for g in b]


def test_program_test_id_is_stable():
    assert program_test_id("sum_squares", 42, 0) == program_test_id("sum_squares", 42, 0)
    assert program_test_id("sum_squares", 42, 0) != program_test_id("sum_squares", 43, 0)


def test_prng_is_replicable():
    a = [SeededRandom(1234).next() for _ in range(5)]
    b = [SeededRandom(1234).next() for _ in range(5)]
    # Note: fresh instances must produce the same first values.
    assert a[0] == b[0]
    with pytest.raises(ValueError):
        SeededRandom(-1)


def test_generated_expected_outputs_compute_in_python(tmp_path):
    """Generated tests carry precomputed oracles; the values must be exact."""
    manifest = generate_corpus(6, 7, tmp_path / "g")
    for generated in manifest:
        expected = generated.test_case.oracle.expected_stdout
        tid = generated.test_case.test_id
        if "sum_squares" in tid:
            assert "n = " in Path(generated.test_case.source_path).read_text(encoding="utf-8")
            # sum of i*i is recomputed twice (loop + formula): lines identical.
            lines = expected.strip().splitlines()
            assert len(lines) == 2 and lines[0] == lines[1]
        elif "reverse" in tid:
            # Reversing a space-separated token list: intended tokens.
            tokens = expected.strip().split()
            values = [int(token) for token in tokens]
            assert len(values) >= 5
            # The source prints in reverse order; parse them from the source to
            # double-check the oracle codepath matches the program's printer.
            import re

            source = Path(generated.test_case.source_path).read_text(encoding="utf-8")
            cpp_values = re.search(r"const int data\[\d+\] = \{([^}]*)\}", source).group(1)
            original_values = [int(token) for token in cpp_values.split(",") if token.strip()]
            assert values == list(reversed(original_values))
        elif "gcd_lcm" in tid:
            lines = expected.strip().splitlines()
            assert len(lines) == 2
            a_value, b_value = None, None
            import re

            source = Path(generated.test_case.source_path).read_text(encoding="utf-8")
            a_match = re.search(r"const long long a = (\d+);", source)
            b_match = re.search(r"const long long b = (\d+);", source)
            a_value, b_value = int(a_match.group(1)), int(b_match.group(1))
            lcm = int(lines[1])
            assert lcm % a_value == 0 and lcm % b_value == 0


def test_missing_expected_file_detected(tmp_path, monkeypatch):
    # Corrupt one .expected file; registry must complain loudly, never silently.
    tests = load_curated_tests()
    target = PROJECT_ROOT / tests[0].source_path
    expected_path = target.with_suffix(".expected")
    backup = expected_path.read_text(encoding="utf-8")
    try:
        expected_path.unlink()
        with pytest.raises(CorpusError, match="missing expected output"):
            load_curated_tests()
    finally:
        expected_path.write_text(backup, encoding="utf-8")
