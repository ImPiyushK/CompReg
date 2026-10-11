"""Unit tests: line-level test-case minimization predicates."""

from __future__ import annotations

from compreg.triage.minimizer import MinimizeResult, minimize_lines


def _text_with_kept(kept_marker: str, dead_lines: int = 30) -> str:
    lines = [f"dead context line {i}" for i in range(dead_lines)]
    lines.append(kept_marker)
    lines += [f"dead tail line {i}" for i in range(10)]
    return "\n".join(lines) + "\n"


def test_reduction_keeps_essential_line():
    text = _text_with_kept("essence: bug present")
    result = minimize_lines(text, lambda candidate: "essence: bug present" in candidate)
    assert isinstance(result, MinimizeResult)
    assert result.reduced
    assert result.minimized.strip() == "essence: bug present"
    assert result.evaluations <= 300


def test_reduction_requires_running_predicate_first():
    text = "keep\nme\n"
    # Predicate rejects even the original text -> nothing is attempted.
    result = minimize_lines(text, lambda c: False)
    assert not result.reduced
    assert result.minimized == text
    assert result.evaluations == 1


def test_unreducible_input_is_preserved_byte_for_byte():
    text = "alpha\nbeta\ngamma\n"
    # Failure only occurs with all three lines: any removal breaks the predicate.
    result = minimize_lines(text, lambda c: c == text)
    assert not result.reduced
    assert result.minimized == text


def test_duplicate_lines_reduce_to_minimum():
    text = "\n".join(["bug"] * 40) + "\n"
    result = minimize_lines(text, lambda c: "bug" in c)
    assert result.reduced
    assert result.minimized.strip() == "bug"


def test_evaluations_budget_respected():
    text = _text_with_kept("target", dead_lines=60)
    result = minimize_lines(text, lambda c: "target" in c, max_evaluations=25)
    assert result.evaluations <= 25


def test_empty_input_is_a_noop():
    result = minimize_lines("", lambda c: True)
    assert not result.reduced
    assert result.minimized == ""


def test_removal_percentage_is_sane():
    text = _text_with_kept("x", dead_lines=50)
    result = minimize_lines(text, lambda c: "x" in c)
    assert 0.0 < result.lines_removed_pct < 100.0
