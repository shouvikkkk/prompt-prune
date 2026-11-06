"""End-to-end CLI tests on real git repos built in temp dirs."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from promptprune.cli import main  # noqa: E402


def _git(cwd: Path, *args: str, env=None) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True,
                   capture_output=True, env=env)


def _repo_with_claude(tmp: Path, text: str, message: str = "Add rules") -> Path:
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "test@example.com")
    _git(tmp, "config", "user.name", "Test Dev")
    (tmp / "CLAUDE.md").write_text(text, encoding="utf-8")
    _git(tmp, "add", "CLAUDE.md")
    _git(tmp, "commit", "-qm", message)
    return tmp


def test_clean_repo_exits_zero(tmp_path, capsys):
    _repo_with_claude(tmp_path, "# Project\n\n- Always run tests.\n")
    assert main(["check", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Nothing to prune" in out


def test_dead_reference_exits_two(tmp_path, capsys):
    _repo_with_claude(
        tmp_path,
        "# Project\n\n- Run `scripts/migrate.sh` before every deploy.\n",
    )
    assert main(["check", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert "scripts/migrate.sh" in out


def test_duplicate_exits_one(tmp_path, capsys):
    _repo_with_claude(
        tmp_path,
        "# Project\n\n"
        "- Always run the full test suite before committing changes.\n"
        "- Always run the full test suite before you commit any changes.\n",
    )
    assert main(["check", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "PRUNE" in out


def test_contradiction_exits_two(tmp_path, capsys):
    _repo_with_claude(
        tmp_path,
        "# Project\n\n"
        "- Always run the full test suite before committing.\n"
        "- Never run the full test suite before committing.\n",
    )
    assert main(["check", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert "CONFLICT" in out


def test_json_output_is_valid(tmp_path, capsys):
    _repo_with_claude(tmp_path, "# Project\n\n- Always run tests.\n")
    assert main(["check", str(tmp_path), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["unit_count"] == 1
    assert data["counts"]["KEEP"] == 1
    assert data["git_known"] is True


def test_no_instruction_files_exits_three(tmp_path, capsys):
    assert main(["check", str(tmp_path)]) == 3


def test_non_git_repo_still_audits(tmp_path, capsys):
    (tmp_path / "CLAUDE.md").write_text(
        "# Project\n\n- Run `scripts/gone.sh` before deploy.\n",
        encoding="utf-8",
    )
    # Dead reference is hard evidence — still exit 2 without git.
    assert main(["check", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert "not a git repository" in out
