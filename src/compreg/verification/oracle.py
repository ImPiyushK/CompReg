"""Output oracles and normalization rules.

Normalization is explicit and configurable: by default only trailing
whitespace per line and trailing blank lines are ignored. Nothing else is
discarded silently - a real mismatch must stay visible.

Float semantics: `float-list` oracles parse numbers in order and compare
them with a relative tolerance plus absolute floor. This isolates honest
contraction/formatting/libm differences (not compiler defects) while
catching anything beyond tolerance.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..models import OracleKind, OracleSpec

_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.\d*(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?|\d+(?:[eE][-+]?\d+)?)")


def normalize_output(text: str, strip_line_whitespace: bool = True) -> str:
    """Apply the documented normalization rules to raw captured stdout."""
    lines = text.split("\n")
    if strip_line_whitespace:
        lines = [line.rstrip() for line in lines]
    # Drop trailing blank lines only; interior blank lines are preserved.
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _parse_numbers(text: str) -> List[float]:
    return [float(match.group(0)) for match in _NUMBER_RE.finditer(text)]


def _numbers_equal(actual: float, expected: float, tolerance: float) -> bool:
    """Relative tolerance comparison with an absolute floor near zero.

    Non-finite values only compare equal to exactly themselves; letting an
    infinite scale enlarge the allowed difference would silently pass
    inf-vs-finite mismatches.
    """
    if actual == expected:
        return True
    if math.isinf(actual) or math.isinf(expected) or math.isnan(actual) or math.isnan(expected):
        return False
    difference = abs(actual - expected)
    scale = max(abs(actual), abs(expected))
    if scale == 0.0:
        return difference <= tolerance
    return difference <= max(tolerance * scale, 5e-324)


@dataclass
class OracleVerdict:
    ok: bool
    reason: str = ""

    def __str__(self) -> str:  # pragma: no cover - display convenience
        return f"{'OK' if self.ok else 'FAIL'}: {self.reason}" if self.reason else ("OK" if self.ok else "FAIL")


def evaluate_oracle(
    oracle: OracleSpec,
    actual_stdout: str,
    actual_exit_code: Optional[int],
    normalize: bool = True,
) -> Tuple[bool, str]:
    """Judge captured output against a spec. Returns (ok, explanation)."""
    if oracle.kind == OracleKind.EXIT_CODE:
        if actual_exit_code != oracle.expected_exit_code:
            return False, f"exit code {actual_exit_code} != expected {oracle.expected_exit_code}"
        return True, "exit code matches"

    expected = normalize_output(oracle.expected_stdout) if (normalize and oracle.normalize_whitespace) else oracle.expected_stdout
    actual = normalize_output(actual_stdout) if (normalize and oracle.normalize_whitespace) else actual_stdout

    if oracle.kind == OracleKind.EXACT:
        if actual == expected:
            return True, "normalized stdout matches"
        return False, _diff_summary(expected, actual)

    if oracle.kind == OracleKind.FLOAT_LIST:
        expected_numbers = _parse_numbers(expected)
        actual_numbers = _parse_numbers(actual)
        if len(expected_numbers) != len(actual_numbers):
            return False, (
                f"number counts differ: expected {len(expected_numbers)}, got {len(actual_numbers)}"
            )
        for index, (want, got) in enumerate(zip(expected_numbers, actual_numbers)):
            if math.isnan(want) or math.isnan(got):
                raise ValueError("oracle comparison received NaN - investigate source determinism")
            if not _numbers_equal(got, want, oracle.tolerance):
                return False, (
                    f"number #{index + 1} differs: expected ~{want!r}, got {got!r} "
                    f"(tolerance {oracle.tolerance})"
                )
        return True, f"{len(expected_numbers)} numbers within tolerance {oracle.tolerance}"

    raise ValueError(f"unknown oracle kind: {oracle.kind}")


def _diff_summary(expected: str, actual: str) -> str:
    """Small, failure-relevant explanation for exact-oracle mismatches."""
    expected_lines = expected.split("\n") if expected else []
    actual_lines = actual.split("\n") if actual else []
    for index in range(max(len(expected_lines), len(actual_lines))):
        want = expected_lines[index] if index < len(expected_lines) else "<missing>"
        got = actual_lines[index] if index < len(actual_lines) else "<missing>"
        if want != got:
            return f"first differing line #{index + 1}: expected {want!r}, got {got!r}"
    return "outputs differ in unspecified way"
