"""Unit tests: output normalization and oracle evaluation."""

from __future__ import annotations

import pytest

from compreg.models import OracleKind, OracleSpec
from compreg.verification.oracle import evaluate_oracle, normalize_output


def test_trailing_whitespace_and_blank_lines_normalized():
    assert normalize_output("a  \nb\t\n\n\n") == "a\nb"
    assert normalize_output("a\n\n\n") == "a"


def test_interior_blank_lines_preserved():
    assert normalize_output("a\n\nb\n") == "a\n\nb"


def test_exact_oracle_matches_normalized():
    oracle = OracleSpec(kind=OracleKind.EXACT, expected_stdout="42\nok\n")
    ok, reason = evaluate_oracle(oracle, "42\nok\n\n", 0)
    assert ok is True


def test_exact_oracle_reports_first_difference():
    oracle = OracleSpec(kind=OracleKind.EXACT, expected_stdout="1\n2\n3\n")
    ok, reason = evaluate_oracle(oracle, "1\n2\n4\n", 0)
    assert ok is False
    assert "line #3" in reason and "'4'" in reason


def test_exact_oracle_detects_missing_trailing_line():
    oracle = OracleSpec(kind=OracleKind.EXACT, expected_stdout="1\n2\n")
    ok, reason = evaluate_oracle(oracle, "1\n", 0)
    assert ok is False


def test_float_list_oracle_tolerance():
    oracle = OracleSpec(kind=OracleKind.FLOAT_LIST, expected_stdout="1.4142135623\n0.5\n", tolerance=1e-9)
    ok, _ = evaluate_oracle(oracle, "1.4142135674\n0.5\n", 0)  # delta 5.1e-9 rel ~ 3.6e-9
    assert ok is False  # outside tight tolerance


def oracle_cases():
    return OracleSpec(kind=OracleKind.FLOAT_LIST, expected_stdout="100.0\n0.0\n", tolerance=1e-6)


def test_float_list_relative_and_zero_handling():
    oracle = oracle_cases()
    ok, _ = evaluate_oracle(oracle, "100.0001\n0.0\n", 0)  # rel delta 1e-6 boundary-ish (1e-6*scale)
    assert ok is True
    ok, _ = evaluate_oracle(oracle, "100.001\n0.0\n", 0)   # rel delta 1e-5 > tolerance
    assert ok is False


def test_float_list_count_mismatch_detected():
    oracle = OracleSpec(kind=OracleKind.FLOAT_LIST, expected_stdout="1\n2\n", tolerance=1e-6)
    ok, reason = evaluate_oracle(oracle, "1\n", 0)
    assert ok is False
    assert "counts differ" in reason


def test_float_list_ignores_labels_but_tracks_order():
    oracle = OracleSpec(kind=OracleKind.FLOAT_LIST, expected_stdout="x=1.5 y=2.25\n", tolerance=1e-9)
    ok, _ = evaluate_oracle(oracle, "x=1.5 y=2.25\n", 0)
    assert ok
    ok, _ = evaluate_oracle(oracle, "x=1.5 y=2.5\n", 0)
    assert not ok


def test_nan_rejected_loudly():
    # The number parser only extracts numeric tokens; overflow exponent must
    # be caught as a normal mismatch rather than raising or silently passing.
    oracle = OracleSpec(kind=OracleKind.FLOAT_LIST, expected_stdout="1000000\n", tolerance=1e-6)
    ok, reason = evaluate_oracle(oracle, "1e999\n", 0)  # parses as inf
    assert ok is False
    assert "number #1" in reason


def test_exit_code_oracle():
    oracle = OracleSpec(kind=OracleKind.EXIT_CODE, expected_exit_code=3)
    ok, _ = evaluate_oracle(oracle, "anything", 3)
    assert ok
    ok, reason = evaluate_oracle(oracle, "anything", 0)
    assert not ok and "exit code 0 != expected 3" in reason
