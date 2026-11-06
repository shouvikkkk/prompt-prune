"""Discovery and segmentation of agent instruction files.

An instruction file is split into *units*: the smallest deletable chunks a
maintainer would actually remove — a bullet, a numbered item, a paragraph,
or a heading section. HTML comments of the form ``<!-- why: ... -->`` are
the rationale comments the Chakrabarti paper proposes; a comment directly
above a unit is attached to it as that unit's rationale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Files that carry agent instructions, in the order a maintainer would
# expect them to be found. Root-level files first, then the per-harness
# locations. ``.cursor/rules/*.md`` and ``.claude/*.md`` are globbed.
INSTRUCTION_FILENAMES = (
    "CLAUDE.md",
    "AGENTS.md",
    "copilot-instructions.md",
    "GEMINI.md",
    "MUSE.md",
)

INSTRUCTION_GLOBS = (
    ".cursor/rules/*.md",
    ".cursor/rules/*.mdc",
    ".claude/*.md",
    ".github/copilot-instructions.md",
    ".github/instructions/*.md",
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
BULLET_RE = re.compile(r"^(\s*)([-*+])\s+(.*)$")
NUMBERED_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
FENCE_RE = re.compile(r"^(\s*)(```|~~~)")
RATIONALE_RE = re.compile(
    r"<!--\s*(?:why|reason|rationale|because)\s*:\s*(.*?)\s*-->", re.IGNORECASE | re.DOTALL
)
COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)


@dataclass
class Unit:
    """One deletable instruction."""

    id: str  # "<file>:<start_line>"
    file: str  # path relative to the scanned root
    start_line: int  # 1-based
    end_line: int  # 1-based, inclusive
    kind: str  # "heading" | "bullet" | "numbered" | "paragraph"
    heading_path: tuple[str, ...] = ()
    text: str = ""  # raw text of the unit (no trailing blank lines)
    rationale: str | None = None  # attached <!-- why: ... --> comment
    code_fenced: bool = False  # unit is (or contains) a fenced code block

    @property
    def normalized(self) -> str:
        """Lower-cased, punctuation-light form used for similarity checks."""
        text = self.text.lower()
        text = re.sub(r"[`*_#>\[\]()]", " ", text)
        text = re.sub(r"[^a-z0-9\s/._-]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @property
    def words(self) -> set[str]:
        return set(self.normalized.split())


def discover_instruction_files(root: Path) -> list[Path]:
    """Return instruction files under *root*, sorted, deduplicated."""
    found: list[Path] = []
    seen: set[Path] = set()
    for name in INSTRUCTION_FILENAMES:
        candidate = root / name
        if candidate.is_file() and candidate not in seen:
            seen.add(candidate)
            found.append(candidate)
    for pattern in INSTRUCTION_GLOBS:
        for candidate in sorted(root.glob(pattern)):
            if candidate.is_file() and candidate not in seen:
                seen.add(candidate)
                found.append(candidate)
    return sorted(found)


def _flush(units: list[Unit], buf: list[str], start: int, end: int, kind: str,
           file_rel: str, heading_path: tuple[str, ...],
           rationale: str | None) -> None:
    text = "\n".join(buf).strip()
    if not text:
        return
    units.append(Unit(
        id=f"{file_rel}:{start}",
        file=file_rel,
        start_line=start,
        end_line=end,
        kind=kind,
        heading_path=heading_path,
        text=text,
        rationale=rationale,
    ))


def parse_file(path: Path, root: Path) -> list[Unit]:
    """Segment one instruction file into units."""
    file_rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    units: list[Unit] = []
    heading_path: list[str] = []
    pending_rationale: str | None = None
    buf: list[str] = []
    buf_start = 0
    buf_kind = "paragraph"
    buf_rationale: str | None = None
    in_fence = False
    fence_char = ""

    def flush(end_line: int) -> None:
        nonlocal buf, buf_start, buf_kind, buf_rationale
        if buf:
            _flush(units, buf, buf_start, end_line, buf_kind, file_rel,
                   tuple(heading_path), buf_rationale)
        buf, buf_start, buf_kind, buf_rationale = [], 0, "paragraph", None

    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(2)
            if not in_fence:
                in_fence, fence_char = True, marker
            elif marker == fence_char:
                in_fence = False
            buf.append(line)
            continue
        if in_fence:
            buf.append(line)
            continue

        # Rationale / HTML comments attach to the *next* unit (or, when they
        # sit inside a unit, to that unit). They never become text.
        if line.strip().startswith("<!--") and line.strip().endswith("-->"):
            match = RATIONALE_RE.search(line)
            if match:
                if buf and buf_rationale is None:
                    buf_rationale = match.group(1).strip()
                elif not buf:
                    pending_rationale = match.group(1).strip()
            continue

        heading = HEADING_RE.match(line)
        if heading:
            flush(i - 1)
            level = len(heading.group(1))
            title = heading.group(2).strip()
            heading_path = heading_path[: level - 1] + [title]
            # A heading is its own unit only when it carries instruction
            # text itself (e.g. "## Never use X"); bare section titles are
            # context, not units.
            buf = [line]
            buf_start = i
            buf_kind = "heading"
            buf_rationale = pending_rationale
            pending_rationale = None
            continue

        bullet = BULLET_RE.match(line)
        numbered = NUMBERED_RE.match(line)
        if bullet or numbered:
            flush(i - 1)
            match = bullet or numbered
            buf = [line]
            buf_start = i
            buf_kind = "bullet" if bullet else "numbered"
            buf_rationale = pending_rationale
            pending_rationale = None
            continue

        if not line.strip():
            flush(i - 1)
            pending_rationale = pending_rationale  # survives blank lines
            continue

        # Continuation of the current unit (paragraph, or the body under a
        # heading that is itself an instruction).
        if not buf:
            buf_start = i
            buf_kind = "paragraph"
            buf_rationale = pending_rationale
            pending_rationale = None
        buf.append(line)

    flush(len(lines))
    # Drop heading units that are bare section titles: a heading whose text
    # is only the title line and which is immediately followed by other
    # units under it carries no instruction of its own.
    pruned: list[Unit] = []
    for idx, unit in enumerate(units):
        if unit.kind == "heading":
            body = unit.text.split("\n", 1)[1].strip() if "\n" in unit.text else ""
            title_only = not body
            # A heading unit only ever holds its own line (we flush on the
            # next heading/bullet/blank), so a heading unit is title-only
            # unless the heading line itself is an imperative instruction.
            if title_only and not _is_imperative_heading(unit):
                continue
        pruned.append(unit)
    return pruned


def _is_imperative_heading(unit: Unit) -> bool:
    """True when a heading line itself states a rule, e.g. '## Never use X'."""
    title = unit.text.lstrip("#").strip().lower()
    return bool(re.match(
        r"^(never|always|do not|don't|must|must not|avoid|prefer|use|no |only )",
        title,
    ))


def parse_root(root: Path) -> tuple[list[Unit], list[Path]]:
    """Parse every instruction file under *root*.

    Returns ``(units, files)``. Files that exist but parse to zero units
    still appear in *files* so the caller can report them.
    """
    files = discover_instruction_files(root)
    units: list[Unit] = []
    for path in files:
        units.extend(parse_file(path, root))
    return units, files
