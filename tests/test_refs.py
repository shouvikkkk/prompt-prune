"""Tests for promptprune.refs — dead-reference detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from promptprune.parse import Unit  # noqa: E402
from promptprune.refs import extract_references, find_dead_refs  # noqa: E402


def _unit(text: str, line: int = 1) -> Unit:
    return Unit(id=f"CLAUDE.md:{line}", file="CLAUDE.md",
                start_line=line, end_line=line, kind="bullet", text=text)


def test_backticked_path_extracted():
    unit = _unit("Run `scripts/migrate.sh` before every deploy.")
    assert extract_references(unit) == ["scripts/migrate.sh"]


def test_url_not_a_reference():
    unit = _unit("See https://example.com/docs/guide.md for details.")
    assert extract_references(unit) == []


def test_plain_words_not_references():
    unit = _unit("Always run the full test suite before committing.")
    assert extract_references(unit) == []


def test_dead_ref_found_and_live_ref_kept(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "deploy.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    live = _unit("Run `scripts/deploy.sh` before every deploy.", 1)
    dead = _unit("Run `scripts/migrate.sh` before every deploy.", 2)
    found = find_dead_refs(tmp_path, [live, dead])
    assert len(found) == 1
    assert found[0].reference == "scripts/migrate.sh"
    assert found[0].unit is dead


def test_directory_reference_is_not_dead(tmp_path):
    (tmp_path / "docs").mkdir()
    unit = _unit("Put design notes in `docs/notes.md` and read `docs` first.", 1)
    found = find_dead_refs(tmp_path, [unit])
    # docs/notes.md is dead; `docs` itself is a live directory.
    assert [f.reference for f in found] == ["docs/notes.md"]
