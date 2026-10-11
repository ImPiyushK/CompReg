"""Terminal summary rendering (plain text, no third-party tables)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..models import TestOutcome

_WIDTH = 96

_CATEGORY_LABELS = {
    "PASS": "pass",
    "COMPILE_ERROR": "compile-error",
    "OUTPUT_MISMATCH": "output-mismatch",
    "NONZERO_EXIT": "nonzero-exit",
    "TIMEOUT": "timeout",
    "EXECUTION_ERROR": "exec-error",
    "INFRASTRUCTURE_ERROR": "infra-error",
    "SKIPPED": "skipped",
}


def divider(title: str = "") -> str:
    return f"== {title} ".ljust(_WIDTH, "=") if title else "=" * _WIDTH


def render_summary(
    title: str,
    outcomes: Sequence[TestOutcome],
    *,
    benchmark_lines: Optional[Iterable[str]] = None,
    regression_lines: Optional[Iterable[str]] = None,
    skipped_notes: Optional[Iterable[str]] = None,
) -> str:
    lines: List[str] = [divider(title), ""]

    counts: Dict[str, int] = {}
    for outcome in outcomes:
        label = _CATEGORY_LABELS.get(outcome.category.value, outcome.category.value)
        counts[label] = counts.get(label, 0) + 1

    total = len(outcomes)
    passed = counts.get("pass", 0)
    skipped = counts.get("skipped", 0)
    failed = total - passed - skipped
    lines.append(f"total={total}  pass={passed}  fail={failed}  skipped={skipped}")
    detail = "  ".join(
        f"{label}={count}" for label, count in sorted(counts.items()) if label != "pass" or True
    )
    lines.append(detail if detail else "(no outcomes)")
    lines.append("")

    failures = [o for o in outcomes if o.is_failure]
    if failures:
        lines.append("failures:")
        for outcome in failures:
            test_id = outcome.test_case.test_id
            config = f"{outcome.identity.family}/{outcome.opt_level}"
            lines.append(f"  [{_CATEGORY_LABELS.get(outcome.category.value, outcome.category.value)}] "
                         f"{test_id} ({config}): {outcome.message[:150]}")
        lines.append("")

    if skipped_notes:
        notes = list(skipped_notes)
        if notes:
            lines.append("skipped configurations:")
            for note in notes:
                lines.append(f"  - {note}")
            lines.append("")

    if benchmark_lines:
        lines.append("benchmarks:")
        for line in benchmark_lines:
            lines.append(f"  {line}")
        lines.append("")

    if regression_lines:
        lines.append("regression verdicts:")
        for line in regression_lines:
            lines.append(f"  {line}")
        lines.append("")

    lines.append(divider())
    return "\n".join(lines)


def render_table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    rows = list(rows)
    widths = [len(str(h)) for h in header]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    def fmt(row: Iterable[str]) -> str:
        return "  ".join(str(cell).ljust(width) for cell, width in zip(row, widths))
    body = [fmt(header)]
    body.append("  ".join("-" * width for width in widths))
    body.extend(fmt(row) for row in rows)
    return "\n".join(body)


def render_bt_table(benchmark_stat_rows: Sequence[Dict[str, Any]]) -> str:
    """Render stored benchmark statistics as a table."""
    header = ("test_id", "opt_level", "samples", "median_s", "min_s", "max_s", "mad_s", "origin")
    rows = [
        (
            stat["test_id"],
            stat.get("opt_level", stat.get("config_hash", "?")),
            str(stat["samples"]),
            f"{stat['median_s']:.4f}",
            f"{stat['min_s']:.4f}",
            f"{stat['max_s']:.4f}",
            f"{stat['mad_s']:.4f}",
            stat.get("origin", "measured"),
        )
        for stat in benchmark_stat_rows
    ]
    return render_table(header, rows)
