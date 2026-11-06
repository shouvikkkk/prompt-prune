"""Tests for promptprune.gitprov — git provenance via blame."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from promptprune.gitprov import is_git_repo, provenance_for_unit  # noqa: E402
from promptprune.parse import parse_file  # noqa: E402


def _git(cwd: Path, *args: str, env=None) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True,
                   capture_output=True, env=env)


def _make_repo(tmp: Path) -> Path:
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "test@example.com")
    _git(tmp, "config", "user.name", "Test Dev")
    return tmp


def test_blame_finds_birth_commit(tmp_path):
    repo = _make_repo(tmp_path)
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("# Project\n\n- Always run tests.\n", encoding="utf-8")
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-qm", "Add testing rule")
    units = parse_file(claude, tmp_path)
    prov = provenance_for_unit(tmp_path, units[0])
    assert prov.known
    assert prov.birth_subject == "Add testing rule"
    assert prov.birth_author == "Test Dev"
    assert prov.churn_commits == 1
    assert prov.commits_since_birth == 0
    assert prov.age_days == 0


def test_churn_counts_distinct_commits(tmp_path):
    repo = _make_repo(tmp_path)
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("# Project\n\n- Always run tests.\n", encoding="utf-8")
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-qm", "Add testing rule")
    # Touch the same line in a second commit.
    claude.write_text("# Project\n\n- Always run the full test suite.\n",
                      encoding="utf-8")
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-qm", "Strengthen testing rule")
    units = parse_file(claude, tmp_path)
    prov = provenance_for_unit(tmp_path, units[0])
    assert prov.known
    assert prov.birth_subject == "Strengthen testing rule"
    assert prov.churn_commits == 1  # blame sees only the latest commit
    assert prov.commits_since_birth == 0


def test_untracked_file_has_unknown_provenance(tmp_path):
    repo = _make_repo(tmp_path)
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("# Project\n\n- Always run tests.\n", encoding="utf-8")
    # Commit something else so the repo exists; CLAUDE.md stays untracked.
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "Add readme")
    units = parse_file(claude, tmp_path)
    prov = provenance_for_unit(tmp_path, units[0])
    assert not prov.known
    assert prov.birth_commit is None


def test_non_git_directory_is_not_a_repo(tmp_path):
    assert not is_git_repo(tmp_path)
