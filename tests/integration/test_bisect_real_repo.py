"""Integration tests: real `git bisect run` against a temporary repository.

These tests exercise the actual bisection workflow (not a mock): commits are
created, a regression is introduced in a known commit, and
`compreg.triage.revision_bisect.bisect_first_bad` must identify that commit.
The predicate contract follows git-bisect(1):

    exit 0 -> good; exit != 0 (except 125) -> bad; 125 -> skip.

Skipped when `git` is unavailable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from compreg.triage.revision_bisect import bisect_first_bad

pytestmark = pytest.mark.slow

_has_git = pytest.mark.skipif(
    __import__("shutil").which("git") is None,
    reason="git executable not found on PATH",
)

# `pytest` wants nothing to do with a name starting with Test* import-wise;
# dataclasses below are plain dicts (no pytest collection side effects).

BISECT_STATE_FILES = (
    "BISECT_LOG",
    "BISECT_START",
    "BISECT_EXPECTED_REV",
    "BISECT_ANCESTORS_OK",
    "BISECT_NAMES",
    "BISECT_RUN",
    "BISECT_TERMS",
)


def _git(repo: Path, *args: str, allowed_codes=(0,)):
    import subprocess

    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in allowed_codes:
        raise AssertionError(
            f"git {' '.join(args)} failed (exit {completed.returncode}): "
            f"{completed.stdout}{completed.stderr}"
        )
    return completed.stdout.strip()


def _make_repo_with_regression(tmp_path: Path) -> tuple:
    """4 commits; the third introduces a REGRESSION_MARKER line, the fourth
    is an innocent change. Returns (repo_path, shas[1..4])."""
    repo = tmp_path / "HistRepo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.name=CompReg Test", "-c", "user.email=test@compreg",
         "commit", "--allow-empty", "-q", "-m", "seed")
    _git(repo, "checkout", "-q", "-b", "history")

    shas = []
    # Commit 1: clean state (good)
    (repo / "state.txt").write_text("initial stable state\n", encoding="utf-8")
    _git(repo, "add", "state.txt")
    _git(repo, "-c", "user.name=CompReg Test", "-c", "user.email=test@compreg",
         "commit", "-qam", "commit 1: stable")
    shas.append(_git(repo, "rev-parse", "HEAD"))

    # Commit 2: benign change (good)
    (repo / "state.txt").write_text("initial stable state\ninline note v2\n", encoding="utf-8")
    _git(repo, "-c", "user.name=CompReg Test", "-c", "user.email=test@compreg",
         "commit", "-qam", "commit 2: benign update")
    shas.append(_git(repo, "rev-parse", "HEAD"))

    # Commit 3: the controlled regression
    (repo / "state.txt").write_text(
        "initial stable state\ninline note v2\nREGRESSION_MARKER: bad behavior\n",
        encoding="utf-8",
    )
    _git(repo, "-c", "user.name=CompReg Test", "-c", "user.email=test@compreg",
         "commit", "-qam", "commit 3: introduce regression")
    bad_regression_sha = _git(repo, "rev-parse", "HEAD")
    shas.append(bad_regression_sha)

    # Commit 4: benign change after the regression (still bad)
    (repo / "state.txt").write_text(
        "initial stable state\ninline note v2\nREGRESSION_MARKER: bad behavior\n"
        "post-regression file polish\n",
        encoding="utf-8",
    )
    _git(repo, "-c", "user.name=CompReg Test", "-c", "user.email=test@compreg",
         "commit", "-qam", "commit 4: post-regression work")
    shas.append(_git(repo, "rev-parse", "HEAD"))

    return repo, shas, bad_regression_sha


def _bug_detector_predicate() -> list[str]:
    """Exit codes follow git-bisect(1): bug present -> 1 (bad); absent -> 0 (good)."""
    py = sys.executable.replace("\\", "/")
    return [
        py, "-c",
        "import sys; "
        "text = open('state.txt', encoding='utf-8').read(); "
        "sys.exit(1 if 'REGRESSION_MARKER' in text else 0)",
    ]


@_has_git
def test_bisect_finds_first_bad_commit_in_real_repo(tmp_path):
    repo, shas, regression_sha = _make_repo_with_regression(tmp_path)
    good_revision = shas[1]          # commit 1 = last known good
    bad_revision = shas[3]           # commit 4 = current bad

    result = bisect_first_bad(
        repo,
        good_revision=good_revision,
        bad_revision=bad_revision,
        predicate_command=_bug_detector_predicate(),
    )

    assert result.ok, f"bisect failed: {result.reason}\nlog: {result.log}"
    # git reports the first bad commit with an abbreviated sha; the injected
    # regression commit must be identified.
    assert result.first_bad_revision is not None
    assert regression_sha.startswith(result.first_bad_revision), (
        f"expected the regression commit {regression_sha[:10]}, got {result.first_bad_revision}"
    )
    # State cleanup after success: no BISECT_* files remain.
    for name in BISECT_STATE_FILES:
        assert not (repo / ".git" / name).exists(), f"{name} leaked after bisect"
    # HEAD is back on the branch (reset went through).
    assert _git(repo, "rev-parse", "HEAD") == bad_revision


@_has_git
def test_bisect_cleanup_when_run_fails(tmp_path):
    """Exit code >= 128 aborts `git bisect run` (git convention). The wrapper
    must report the failure AND clean up the bisect state afterwards.

    Note: an all-good predicate does NOT fail the run - git treats the
    declared bad endpoint as the first bad commit. The abort exit code is the
    deterministic way to make `bisect run` fail.
    """
    repo, shas, regression_sha = _make_repo_with_regression(tmp_path)
    aborting_predicate = [sys.executable, "-c", "import sys; sys.exit(128)"]

    result = bisect_first_bad(
        repo,
        good_revision=shas[1],
        bad_revision=shas[3],
        predicate_command=aborting_predicate,
    )

    assert result.ok is False
    assert result.reason
    assert result.first_bad_revision is None
    for name in BISECT_STATE_FILES:
        assert not (repo / ".git" / name).exists(), f"{name} leaked after failed bisect"


@_has_git
def test_bisect_reports_missing_revisions_and_cleans_state(tmp_path):
    repo, shas, _ = _make_repo_with_regression(tmp_path)
    result = bisect_first_bad(
        repo,
        good_revision="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        bad_revision=shas[3],
        predicate_command=_bug_detector_predicate(),
    )
    assert result.ok is False
    assert "revision not found" in result.reason
    for name in BISECT_STATE_FILES:
        assert not (repo / ".git" / name).exists()
