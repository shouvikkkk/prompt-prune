"""Tests for promptprune.similarity — duplicates and contradictions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from promptprune.parse import Unit  # noqa: E402
from promptprune.similarity import (  # noqa: E402
    find_contradictions,
    find_near_duplicates,
)


def _unit(text: str, line: int = 1) -> Unit:
    return Unit(id=f"CLAUDE.md:{line}", file="CLAUDE.md",
                start_line=line, end_line=line, kind="bullet", text=text)


def test_near_duplicate_detected():
    a = _unit("Always run the full test suite before committing changes.", 1)
    b = _unit("Always run the full test suite before you commit any changes.", 2)
    found = find_near_duplicates([a, b])
    assert len(found) == 1
    assert found[0].kind == "NEAR-DUPLICATE"


def test_unrelated_units_not_duplicates():
    a = _unit("Always run the full test suite before committing changes.", 1)
    b = _unit("Use tabs for indentation in Go files.", 2)
    assert find_near_duplicates([a, b]) == []


def test_contradiction_detected():
    a = _unit("Always run the full test suite before committing.", 1)
    b = _unit("Never run the full test suite before committing.", 2)
    found = find_contradictions([a, b])
    assert len(found) == 1
    assert found[0].kind == "CONTRADICTION"
    assert "suite" in found[0].evidence and "test" in found[0].evidence


def test_scoped_rules_not_flagged_as_contradiction():
    a = _unit("Always run the full test suite locally before committing.", 1)
    b = _unit("Never run the full test suite in CI before committing.", 2)
    assert find_contradictions([a, b]) == []


def test_same_direction_rules_not_contradiction():
    a = _unit("Always run the linter before committing.", 1)
    b = _unit("You must run the linter before every commit.", 2)
    assert find_contradictions([a, b]) == []
