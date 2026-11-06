"""Git provenance for instruction units.

For every unit we recover, from ``git blame``, the commit that introduced
each of its lines, then take the *earliest* of those commits as the unit's
birth: the commit whose message is the closest thing the repo has to a
rationale for the rule. Churn — the number of distinct commits touching the
unit — tells whether the rule is actively maintained or untouched since
birth. Everything here is read-only; a repo without git, or a file that is
untracked, yields ``UNKNOWN`` provenance rather than a fabricated date.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .parse import Unit


@dataclass
class Provenance:
    birth_commit: str | None = None  # full sha, or None when unknown
    birth_short: str | None = None
    birth_author: str | None = None
    birth_date: datetime | None = None
    birth_subject: str | None = None  # commit message subject line
    churn_commits: int = 0  # distinct commits touching the unit's lines
    commits_since_birth: int | None = None
    known: bool = False

    @property
    def age_days(self) -> int | None:
        if self.birth_date is None:
            return None
        return (datetime.now(timezone.utc) - self.birth_date).days


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result


def is_git_repo(root: Path) -> bool:
    result = _git(root, "rev-parse", "--is-inside-work-tree")
    return result is not None and result.returncode == 0


def _blame_lines(root: Path, rel_file: str, start: int, end: int) -> list[dict]:
    """``git blame --line-porcelain`` for one line range.

    Returns one dict per line: {sha, author, author_time (epoch int)}.
    Empty list when the file is untracked, git is missing, or blame fails.
    """
    result = _git(
        root, "blame", "--line-porcelain",
        "-L", f"{start},{end}", "--", rel_file,
    )
    if result is None or result.returncode != 0:
        return []
    entries: list[dict] = []
    current: dict = {}
    for line in result.stdout.splitlines():
        if len(line) >= 40 and line[40:41] == " " and all(
            c in "0123456789abcdef" for c in line[:40]
        ):
            if current:
                entries.append(current)
            current = {"sha": line[:40]}
        elif line.startswith("author "):
            current["author"] = line[len("author "):]
        elif line.startswith("author-time "):
            try:
                current["author_time"] = int(line[len("author-time "):])
            except ValueError:
                current["author_time"] = 0
    if current:
        entries.append(current)
    return entries


def provenance_for_unit(root: Path, unit: Unit) -> Provenance:
    """Birth commit, author, date, churn and commits-since-birth for a unit."""
    entries = _blame_lines(root, unit.file, unit.start_line, unit.end_line)
    if not entries:
        return Provenance()
    # Birth = the earliest line-introducing commit in the unit.
    birth = min(entries, key=lambda e: e.get("author_time", 0))
    sha = birth["sha"]
    prov = Provenance(
        birth_commit=sha,
        birth_short=sha[:7],
        birth_author=birth.get("author"),
        birth_date=datetime.fromtimestamp(
            birth.get("author_time", 0), tz=timezone.utc
        ) if birth.get("author_time") else None,
        churn_commits=len({e["sha"] for e in entries}),
        known=True,
    )
    subject = _git(root, "log", "-1", "--format=%s", sha)
    if subject is not None and subject.returncode == 0:
        prov.birth_subject = subject.stdout.strip() or None
    count = _git(root, "rev-list", "--count", f"{sha}..HEAD")
    if count is not None and count.returncode == 0:
        try:
            prov.commits_since_birth = int(count.stdout.strip())
        except ValueError:
            pass
    return prov


def file_growth(root: Path, rel_file: str) -> dict:
    """Rough growth facts for one instruction file from its git history.

    Returns commits touching the file, first-commit date, and the number of
    instruction-looking lines (+/-) across its history is deliberately NOT
    attempted: ``git log --numstat`` cannot see inside markdown semantics,
    and a fabricated growth curve would be worse than none. The caller
    reports what is here and nothing more.
    """
    count = _git(root, "log", "--oneline", "--follow", "--", rel_file)
    if count is None or count.returncode != 0:
        return {"commits": 0, "known": False}
    lines = [line for line in count.stdout.splitlines() if line.strip()]
    first = _git(root, "log", "--reverse", "--format=%aI", "--", rel_file)
    first_date = None
    if first is not None and first.returncode == 0 and first.stdout.strip():
        first_date = first.stdout.splitlines()[0].strip()
    return {"commits": len(lines), "known": True, "first_commit_date": first_date}
