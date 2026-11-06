"""Tests for promptprune.parse — segmentation of instruction files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from promptprune.parse import parse_file, parse_root  # noqa: E402


def _write(tmp: Path, name: str, text: str) -> Path:
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_bullets_become_units(tmp_path):
    path = _write(tmp_path, "CLAUDE.md", """# Project

- Always run the full test suite before committing.
- Never commit directly to main.
""")
    units = parse_file(path, tmp_path)
    assert [u.kind for u in units] == ["bullet", "bullet"]
    assert "full test suite" in units[0].text
    assert units[0].heading_path == ("Project",)


def test_bare_section_heading_is_not_a_unit(tmp_path):
    path = _write(tmp_path, "AGENTS.md", """# Rules

## Style

- Use tabs for indentation.
""")
    units = parse_file(path, tmp_path)
    assert len(units) == 1
    assert units[0].kind == "bullet"
    assert units[0].heading_path == ("Rules", "Style")


def test_imperative_heading_is_a_unit(tmp_path):
    path = _write(tmp_path, "CLAUDE.md", """# Project

## Never use rm -rf

- Prefer git clean.
""")
    units = parse_file(path, tmp_path)
    assert units[0].kind == "heading"
    assert "Never use rm -rf" in units[0].text


def test_rationale_comment_attaches_to_next_unit(tmp_path):
    path = _write(tmp_path, "CLAUDE.md", """# Project

<!-- why: the linter crashes on tabs -->
- Use spaces for indentation.
""")
    units = parse_file(path, tmp_path)
    assert units[0].rationale == "the linter crashes on tabs"


def test_code_fence_stays_inside_unit(tmp_path):
    path = _write(tmp_path, "CLAUDE.md", """# Project

Run the migration like this:

```bash
./scripts/migrate.sh
```

- Never run it twice.
""")
    units = parse_file(path, tmp_path)
    texts = [u.text for u in units]
    assert any("migrate.sh" in t for t in texts)
    assert any("Never run it twice" in t for t in texts)


def test_numbered_items_and_paragraphs(tmp_path):
    path = _write(tmp_path, "CLAUDE.md", """# Project

Follow the deploy checklist.

1. Build the image.
2. Push to the registry.
""")
    units = parse_file(path, tmp_path)
    kinds = [u.kind for u in units]
    assert kinds == ["paragraph", "numbered", "numbered"]


def test_parse_root_discovers_cursor_rules(tmp_path):
    _write(tmp_path, "CLAUDE.md", "- One.\n")
    _write(tmp_path, ".cursor/rules/testing.md", "- Two.\n")
    units, files = parse_root(tmp_path)
    assert len(units) == 2
    assert len(files) == 2
