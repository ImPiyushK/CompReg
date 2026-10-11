"""Line-level delta-debugging test-case minimization.

Scope and limitations (documented honestly):
  * Input type: plain-text source files. The reducer works on LINES only -
    it does not parse the language, so it cannot split a line, reorder
    lines, or substitute tokens.
  * A candidate "preserves the failure" when the caller-provided predicate
    returns True for the candidate's text.
  * Removing lines usually changes compilation. The bundled compile-and-run
    predicate (see cli.py) treats a compile failure as NOT preserving a
    runtime failure; a candidate must reproduce the same failure signature.
  * If no reduction satisfies the predicate, the original input is returned
    unchanged with reduced=False.

Algorithm: delta debugging over line blocks with growing granularity,
bounded by an evaluation budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

Predicate = Callable[[str], bool]


@dataclass
class MinimizeResult:
    original: str
    minimized: str
    reduced: bool
    evaluations: int
    removed_lines: int

    @property
    def lines_removed_pct(self) -> float:
        original_lines = len(self.original.splitlines()) or 1
        return self.removed_lines / original_lines * 100.0


def minimize_lines(
    source_text: str,
    predicate: Predicate,
    *,
    initial_chunks: int = 3,
    max_evaluations: int = 300,
) -> MinimizeResult:
    """Reduce `source_text` line-wise while the predicate keeps holding.

    The predicate is called on candidate texts derived from the ORIGINAL
    text base (never accumulated on top of failed candidates).
    """
    evaluations = 0

    if not source_text.strip():
        return MinimizeResult(source_text, source_text, False, 0, 0)
    if not predicate(source_text):
        return MinimizeResult(source_text, source_text, False, 1, 0)
    evaluations = 1

    current: List[str] = source_text.splitlines()
    original_count = len(current)
    removed_total = 0
    granularity = max(2, min(initial_chunks, len(current)))

    def candidate_text_from(kept_lines: List[str]) -> str:
        if not kept_lines:
            return ""
        return "\n".join(kept_lines) + "\n"

    reduced_any = False
    while len(current) >= 1 and evaluations < max_evaluations:
        bump = max(1, len(current) // granularity)
        spans: List[tuple[int, int]] = []
        start = 0
        while start < len(current):
            spans.append((start, min(start + bump, len(current))))
            start += bump

        changed = False
        for (start, stop) in spans:
            if len(current) <= 1 or evaluations >= max_evaluations:
                break
            drop = set(range(start, stop))
            kept = [line for pos, line in enumerate(current) if pos not in drop]
            text = candidate_text_from(kept)
            holds = predicate(text)
            evaluations += 1
            if holds:
                current = kept
                removed_total += stop - start
                changed = True
                reduced_any = True
                granularity = max(2, granularity // 2)
                break

        if changed:
            continue
        if len(current) <= 1:
            break
        if granularity >= 2 * len(current):
            break  # cannot go finer with line-unit granularity
        granularity = min(granularity * 2, 2 * len(current))

    minimized = candidate_text_from(current)
    was_reduced = reduced_any and minimized != source_text
    return MinimizeResult(
        original=source_text,
        minimized=minimized,
        reduced=was_reduced,
        evaluations=evaluations,
        removed_lines=removed_total,
    )
