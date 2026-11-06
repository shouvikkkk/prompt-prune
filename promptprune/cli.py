"""CLI for prompt-prune.

Usage:
    prompt-prune check <path> [--format text|json] [--min-similarity 0.7]
    prompt-prune check --help

Exit codes: 0 nothing to prune · 1 PRUNE/REVIEW suggestions · 2
contradictions or dead references · 3 no instruction files / no git.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .gitprov import is_git_repo, provenance_for_unit
from .parse import parse_root
from .refs import find_dead_refs
from .report import EXIT_FAIL, EXIT_OK, EXIT_REVIEW, EXIT_UNKNOWN, Report
from .score import score_units
from .similarity import find_contradictions, find_near_duplicates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prompt-prune",
        description=(
            "Provenance-aware pruner for agent instruction files "
            "(CLAUDE.md, AGENTS.md, ...). Finds rules that are safe to "
            "delete, contradict each other, or reference things that no "
            "longer exist."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser(
        "check",
        help="audit the instruction files under a path",
        description=(
            "Audit instruction files under PATH. Exit 0: nothing to prune. "
            "Exit 1: PRUNE/REVIEW suggestions. Exit 2: contradictions or "
            "dead references. Exit 3: no instruction files found."
        ),
    )
    check.add_argument("path", type=Path, help="repo root or directory to audit")
    check.add_argument("--format", choices=["text", "json"], default="text")
    check.add_argument(
        "--min-similarity", type=float, default=0.70,
        help="token-Jaccard threshold for near-duplicates (default 0.70)",
    )
    check.add_argument(
        "--no-git", action="store_true",
        help="skip git provenance even inside a repository",
    )
    return parser


def run_check(args: argparse.Namespace) -> int:
    root = args.path.resolve()
    if not root.is_dir():
        print(f"prompt-prune: {root} is not a directory", file=sys.stderr)
        return EXIT_UNKNOWN
    units, files = parse_root(root)
    if not files:
        print(
            f"prompt-prune: no instruction files found under {root}\n"
            "looked for CLAUDE.md, AGENTS.md, copilot-instructions.md, "
            "GEMINI.md, MUSE.md, .cursor/rules/*.md, .claude/*.md, "
            ".github/copilot-instructions.md",
            file=sys.stderr,
        )
        return EXIT_UNKNOWN

    git_known = is_git_repo(root) and not args.no_git
    provenances = {}
    if git_known:
        for unit in units:
            provenances[unit.id] = provenance_for_unit(root, unit)

    duplicates = find_near_duplicates(units, min_jaccard=args.min_similarity)
    contradictions = find_contradictions(units)
    dead_refs = find_dead_refs(root, units)
    verdicts = score_units(units, provenances, duplicates, contradictions, dead_refs)

    if any(v.verdict == "CONFLICT" for v in verdicts) or dead_refs:
        exit_code = EXIT_FAIL
    elif any(v.verdict in ("PRUNE", "REVIEW") for v in verdicts):
        exit_code = EXIT_REVIEW
    else:
        exit_code = EXIT_OK

    report = Report(
        root=str(root),
        files=[str(f) for f in files],
        units=units,
        verdicts=verdicts,
        git_known=git_known,
        exit_code=exit_code,
    )
    print(report.to_json() if args.format == "json" else report.text())
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "check":
        return run_check(args)
    return EXIT_UNKNOWN


if __name__ == "__main__":
    sys.exit(main())
