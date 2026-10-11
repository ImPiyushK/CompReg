"""Git revision bisection (optional capability, explicit about limits).

`git bisect run` interprets the predicate command's exit codes with Git's
own documented semantics (git-bisect(1)):

  0                  -> good revision (failure does NOT reproduce)
  125                -> skip this revision (untestable)
  any other nonzero  -> bad revision (failure reproduces; codes >= 128 abort)

So a predicate that looks for the bug should exit NONZERO when the bug is
present and 0 when it is absent - the usual form is `! <failure-detector>`.
The wrapper passes the command to git untouched and parses the resulting
"<sha> is the first bad commit" line.

If the working tree is not a git repository, the revisions do not exist, or
git itself is unavailable, the returned result states the limitation
instead of pretending to bisect. Bisect state (`git bisect start`) is
always cleaned up with `git bisect reset`, on success and on failure.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence


@dataclass
class BisectResult:
    ok: bool
    first_bad_revision: Optional[str] = None
    log: List[str] = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def unavailable_reason(self) -> Optional[str]:
        return self.reason if not self.ok else None


def _git(repo_dir: Path, args: Sequence[str], timeout: float = 120.0) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return completed.returncode, (completed.stdout + completed.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"git invocation failed: {exc}"


def bisect_first_bad(
    repo_dir: str | Path,
    good_revision: str,
    bad_revision: str,
    predicate_command: Sequence[str],
) -> BisectResult:
    """Bisect between two revisions using `predicate_command` as the oracle.

    `predicate_command` runs in each checked-out revision under
    `git bisect run` and is interpreted BY GIT with its standard contract:

      * exit 0                  -> revision is good (failure not reproduced)
      * exit 125                -> skip the revision
      * any other nonzero exit  -> revision is bad (failure reproduced);
        per git conventions, exit codes >= 128 abort the entire run

    Therefore a detector for the bug itself should exit nonzero when the
    bug is present and 0 when it is not (e.g. `! python check_bug.py`).
    """
    repo = Path(repo_dir)
    if not repo.is_dir():
        return BisectResult(ok=False, reason=f"repository path not found: {repo}")

    code, _ = _git(repo, ["rev-parse", "HEAD"])
    if code != 0:
        return BisectResult(ok=False, reason="not a git repository (git rev-parse HEAD failed)")

    for revision in (good_revision, bad_revision):
        code, _ = _git(repo, ["rev-parse", "--verify", f"{revision}^{{commit}}"])
        if code != 0:
            return BisectResult(ok=False, reason=f"revision not found: {revision}")

    code, log_text = _git(repo, ["bisect", "reset"])
    log_list = [log_text] if log_text else []

    code, log_text = _git(repo, ["bisect", "start", bad_revision, good_revision])
    log_list.append(log_text)
    if code != 0:
        _git(repo, ["bisect", "reset"])
        return BisectResult(ok=False, reason=f"git bisect start failed: {log_text}", log=log_list)

    argv: List[str] = ["bisect", "run", *predicate_command]
    code, log_text = _git(repo, argv, timeout=3 * 3600.0)
    log_list.append(log_text)

    first_bad: Optional[str] = None
    for line in log_text.splitlines():
        if "is the first bad commit" in line:
            first_bad = line.split()[0]
            break

    if code == 0 and first_bad:
        result = BisectResult(ok=True, first_bad_revision=first_bad, log=log_list)
    elif code != 0:
        result = BisectResult(
            ok=False,
            reason=f"git bisect run failed (exit {code}); requires a deterministic, "
            "always-executable predicate command",
            log=log_list,
        )
    else:
        result = BisectResult(
            ok=False,
            reason="bisect completed but no failing revision was determined; "
            "the predicate may not reproduce on candidate revisions",
            log=log_list,
        )

    code, log_text = _git(repo, ["bisect", "reset"])
    if log_text:
        log_list.append(log_text)
    return result


def check_bisect_capability(repo_dir: str | Path) -> tuple[bool, Optional[str]]:
    """Human-usable check used by doctor/help: can revision bisection run here?"""
    repo = Path(repo_dir)
    if not repo.is_dir():
        return False, f"repository path not found: {repo}"
    import shutil

    if shutil.which("git") is None:
        return False, "git executable not found on PATH"
    code, _ = _git(repo, ["rev-parse", "HEAD"])
    if code != 0:
        return False, "not a git repository"
    return True, None
