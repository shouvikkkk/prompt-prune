"""Dead-reference detection: do the files, directories and commands a rule
names still exist?

A rule like "Run `scripts/migrate.sh` before every deploy" is actively
harmful once ``scripts/migrate.sh`` has been deleted — the agent either
fails or, worse, improvises. We extract candidate paths from backticked
spans and bare path-like tokens, then resolve each against the repo root.
Only tokens that look like paths (contain a ``/`` and a file extension, or
match a known directory layout) are checked; URLs, commands and plain
words are never flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .parse import Unit

BACKTICK_RE = re.compile(r"`([^`]+)`")
# Bare path-like tokens: src/foo.py, docs/guide.md, tests/test_x.py
BARE_PATH_RE = re.compile(
    r"(?<![\w/])([a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)+"
    r"(?:\.[a-zA-Z0-9]{1,10})?)(?![\w/])"
)
URL_RE = re.compile(r"https?://\S+|www\.\S+")
# Extensions that make a bare token plausibly a file rather than a phrase.
FILE_EXTENSIONS = frozenset("""
py js ts tsx jsx mjs cjs json yaml yml toml ini cfg conf md rst txt sh bash
zsh sql html css scss lock csv xml svg png jpg jpeg gif pdf go rs java kt
rb php pl ex exs hs ml c h cpp hpp cs swift dart lua r jl
""".split())


@dataclass
class DeadRef:
    unit: Unit
    reference: str
    kind: str  # "file" | "directory"


def _looks_like_path(token: str) -> bool:
    if "/" not in token:
        return False
    if token.startswith(("-", "--")):
        return False
    parts = token.split("/")
    if any(p in ("", ".", "..") for p in parts[:-1]):
        return False
    last = parts[-1]
    if "." in last and last.rsplit(".", 1)[1].lower() in FILE_EXTENSIONS:
        return True
    # Extensionless but deep (src/lib/foo) — plausibly a module path.
    return len(parts) >= 3 and all(re.match(r"^[\w.-]+$", p) for p in parts)


def extract_references(unit: Unit) -> list[str]:
    """Candidate path references mentioned in one unit, deduplicated."""
    text = URL_RE.sub(" ", unit.text)
    found: list[str] = []
    seen: set[str] = set()
    for match in BACKTICK_RE.finditer(text):
        token = match.group(1).strip().strip("'\"")
        if _looks_like_path(token) and token not in seen:
            seen.add(token)
            found.append(token)
    for match in BARE_PATH_RE.finditer(text):
        token = match.group(1)
        if _looks_like_path(token) and token not in seen:
            seen.add(token)
            found.append(token)
    return found


def find_dead_refs(root: Path, units: list[Unit]) -> list[DeadRef]:
    """References in the units that no longer exist under *root*."""
    dead: list[DeadRef] = []
    for unit in units:
        for ref in extract_references(unit):
            target = (root / ref).resolve()
            try:
                target.relative_to(root.resolve())
            except ValueError:
                continue  # escapes the repo (e.g. ../x) — not our call
            if target.is_dir():
                continue
            if not target.exists():
                # A path whose last segment has no extension may be a
                # directory that was renamed; only call it dead when it
                # looked like a file (extension) or a deep module path.
                dead.append(DeadRef(unit=unit, reference=ref, kind="file"))
    return dead
