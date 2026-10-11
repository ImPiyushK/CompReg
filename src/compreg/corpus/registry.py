"""Curated test-corpus registry.

Each entry couples a trusted source file with a validation oracle. Expected
outputs live in sidecar `.expected` files next to the sources so they are
reviewable artifacts in version control rather than string literals in code.

Correctness policy:
  * Every oracle is an independently derived expectation (hand-verified
    arithmetic, or a standalone reference model). Two compilers agreeing is
    informational only and is never the pass criterion for these tests.
  * Sources must be deterministic, free of undefined behavior, and bounded
    in runtime.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ..models import OracleKind, OracleSpec, TestCase
from ..util import sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CORPUS_ROOT = PROJECT_ROOT / "test_corpus"


@dataclass(frozen=True)
class CorpusEntry:
    test_id: str
    category: str
    description: str
    oracle_kind: OracleKind = OracleKind.EXACT
    timeout_s: float = 10.0
    benchmark_eligible: bool = False
    benchmark_version: Optional[str] = None
    tolerance: float = 1e-9


# --------------------------------------------------------------------- #
# The registry table. One row per curated source; expected outputs are in
# <source-dir>/<name>.expected.
# --------------------------------------------------------------------- #
CURATED: List[CorpusEntry] = [
    # --- arithmetic -----------------------------------------------------
    CorpusEntry("arithmetic_int_basic", "arithmetic",
                "Signed/unsigned integer arithmetic with independently verified values."),
    CorpusEntry("arithmetic_sum_series", "arithmetic",
                "Long long series sums against closed-form formulas."),
    CorpusEntry("arithmetic_float_basic", "arithmetic",
                "IEEE double ops and libm functions; tolerant numeric oracle.",
                oracle_kind=OracleKind.FLOAT_LIST, tolerance=1e-9),
    # --- loops ------------------------------------------------------------
    CorpusEntry("loops_fizzbuzz", "loops",
                "Divisibility branching over 1..45."),
    CorpusEntry("loops_collatz_lengths", "loops",
                "3n+1 chain lengths; includes the known length-111 chain for 27."),
    CorpusEntry("loops_nested_reduce", "loops",
                "Two-kernel 1D convolution and a correlate channel; values "
                "verified against an independent Python model."),
    # --- arrays -----------------------------------------------------------
    CorpusEntry("arrays_reverse_copy", "arrays",
                "Reverse copy plus round-trip equivalence check."),
    CorpusEntry("arrays_matrix_transpose", "arrays",
                "Transpose of a fixed 3x4 matrix."),
    CorpusEntry("arrays_histogram", "arrays",
                "Bounded-value histogram with total count check."),
    # --- branches ---------------------------------------------------------
    CorpusEntry("branches_grade_classifier", "branches",
                "Multi-way grading with documented 89/90 boundary behavior."),
    CorpusEntry("branches_sign_classifier", "branches",
                "Sign classification including negative minima."),
    # --- boundary ---------------------------------------------------------
    CorpusEntry("boundary_int_limits", "boundary",
                "Integer limits and well-defined unsigned wrap-around."),
    CorpusEntry("boundary_guarded_division", "boundary",
                "Division guarded at zero denominators."),
    CorpusEntry("boundary_array_edges", "boundary",
                "In-bounds first/last element access with guarded neighbors."),
    # --- sorting ----------------------------------------------------------
    CorpusEntry("sorting_bubble_sort", "sorting",
                "Bubble sort with sorted-flag and checksum invariants."),
    CorpusEntry("sorting_insertion_sort", "sorting",
                "Insertion sort with sorted-flag and checksum invariants."),
    CorpusEntry("sorting_binary_search", "sorting",
                "Binary search over hits, misses and edges."),
    # --- bitwise ----------------------------------------------------------
    CorpusEntry("bitwise_rotate_popcount", "bitwise",
                "Guarded rotate (r==0 safe), manual popcount."),
    CorpusEntry("bitwise_mask_ops", "bitwise",
                "Set/clear/test and lowest/highest set-bit isolation."),
    # --- structs ----------------------------------------------------------
    CorpusEntry("structs_student_records", "structs",
                "Aggregate structs with averages and class statistics."),
    CorpusEntry("structs_point_distance", "structs",
                "Struct arithmetic with doubles; tolerant numeric oracle.",
                oracle_kind=OracleKind.FLOAT_LIST, tolerance=1e-6),
    # --- recursion --------------------------------------------------------
    CorpusEntry("recursion_fib_memo", "recursion",
                "Memoized recursive Fibonacci with known values."),
    CorpusEntry("recursion_ackermann_small", "recursion",
                "Bounded Ackermann values (largest input: ack(3,3)=61)."),
    # --- strings ----------------------------------------------------------
    CorpusEntry("strings_char_ops", "strings",
                "Bounded C-string length/upper/reverse/vowel operations."),
    # --- benchmarks -------------------------------------------------------
    CorpusEntry("bench_matrix", "benches",
                "Dense double matrix multiply; checksum via tolerant numeric "
                "oracle (contraction differences are not compiler defects).",
                oracle_kind=OracleKind.FLOAT_LIST, tolerance=1e-6,
                benchmark_eligible=True, benchmark_version="v1"),
    CorpusEntry("bench_int_workload", "benches",
                "Integer mixing chain; checksum verified exactly against an "
                "independent Python reference model.",
                benchmark_eligible=True, benchmark_version="v1"),
]


class CorpusError(Exception):
    """Raised when the on-disk corpus cannot satisfy the registry."""


def load_curated_tests() -> List[TestCase]:
    """Materialize the curated table into TestCase records.

    Raises CorpusError when a source or its .expected file is missing, is
    listed twice, or a benchmark entry lacks a version.
    """
    tests: List[TestCase] = []
    seen: Dict[str, str] = {}
    for entry in CURATED:
        source = _find_source(entry.test_id, entry.category)
        if source is None:
            raise CorpusError(f"no source file for test '{entry.test_id}'")
        if entry.test_id in seen:
            raise CorpusError(f"duplicate test id '{entry.test_id}' in {seen[entry.test_id]}")
        seen[entry.test_id] = source

        if entry.benchmark_eligible and not entry.benchmark_version:
            raise CorpusError(f"benchmark test '{entry.test_id}' lacks benchmark_version")

        oracle = OracleSpec(
            kind=entry.oracle_kind,
            expected_stdout=_expected_output(entry),
            expected_exit_code=0,
            tolerance=entry.tolerance,
        )
        tests.append(
            TestCase(
                test_id=entry.test_id,
                source_path=source,
                category=entry.category,
                description=entry.description,
                oracle=oracle,
                timeout_s=entry.timeout_s,
                benchmark_eligible=entry.benchmark_eligible,
                benchmark_version=entry.benchmark_version,
            )
        )
    return tests


def load_ad_hoc_test(
    source_path: str | Path,
    expected_stdout: str = "",
    oracle_kind: OracleKind = OracleKind.EXACT,
    tolerance: float = 1e-9,
    timeout_s: float = 10.0,
    test_id: str | None = None,
) -> TestCase:
    """Create a TestCase from an arbitrary source (demos/CI fixtures).

    The test id is stable for a given source content hash, so repeated runs
    map to the same registry rows.
    """
    path = Path(source_path).resolve()
    if not path.is_file():
        raise CorpusError(f"ad-hoc test source not found: {path}")
    if not isinstance(oracle_kind, OracleKind):
        oracle_kind = OracleKind(oracle_kind)
    digest = sha256_file(path)[:10]
    tid = test_id or f"adhoc_{path.stem}_{digest}"
    relative = _relative_to_project(path)
    return TestCase(
        test_id=tid,
        source_path=relative,
        category="ad-hoc",
        description=f"ad-hoc test from {relative}",
        oracle=OracleSpec(kind=oracle_kind, expected_stdout=expected_stdout,
                          tolerance=tolerance, expected_exit_code=0),
        timeout_s=timeout_s,
    )


def _find_source(test_id: str, category: str) -> Optional[str]:
    """Locate `<test_id>.cpp` inside its category directory."""
    candidate = CORPUS_ROOT / category / f"{test_id}.cpp"
    if candidate.is_file():
        return _relative_to_project(candidate)
    return None


def _expected_output(entry: CorpusEntry) -> str:
    if entry.oracle_kind == OracleKind.EXIT_CODE:
        return ""
    path = Path(_find_source(entry.test_id, entry.category) or "")
    expected_path = path.with_suffix(".expected")
    if not expected_path.is_absolute():
        expected_path = PROJECT_ROOT / path.with_suffix(".expected")
    if not expected_path.is_file():
        raise CorpusError(
            f"missing expected output file for '{entry.test_id}': {expected_path}\n"
            f"Every registry entry needs a reviewed .expected artifact."
        )
    return expected_path.read_text(encoding="utf-8")


def _relative_to_project(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT))
    except ValueError:  # outside the project tree (ad-hoc/generated)
        return str(path)


def test_source_abs_path(test: TestCase) -> Path:
    """Absolute path of a test's source file."""
    path = Path(test.source_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def registry_stats() -> Dict[str, int]:
    """Counts by category for reporting."""
    counts: Dict[str, int] = {}
    for entry in CURATED:
        counts[entry.category] = counts.get(entry.category, 0) + 1
    counts["total"] = len(CURATED)
    counts["benchmarks"] = sum(1 for e in CURATED if e.benchmark_eligible)
    return counts
