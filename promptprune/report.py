"""Text and JSON reports for a prompt-prune run."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .gitprov import Provenance
from .parse import Unit
from .score import UnitVerdict

EXIT_OK = 0      # nothing to prune, no conflicts
EXIT_REVIEW = 1  # PRUNE/REVIEW suggestions exist
EXIT_FAIL = 2    # contradictions or dead references found
EXIT_UNKNOWN = 3  # no instruction files, or git provenance unavailable


@dataclass
class Report:
    root: str
    files: list[str]
    units: list[Unit]
    verdicts: list[UnitVerdict]
    git_known: bool
    exit_code: int

    @property
    def counts(self) -> dict[str, int]:
        out = {"KEEP": 0, "REVIEW": 0, "PRUNE": 0, "CONFLICT": 0}
        for v in self.verdicts:
            out[v.verdict] += 1
        return out

    @property
    def total_chars(self) -> int:
        return sum(len(u.text) for u in self.units)

    @property
    def estimated_tokens(self) -> int:
        # ~4 chars/token is the standard rough estimate for English prose.
        return self.total_chars // 4

    def text(self) -> str:
        lines: list[str] = []
        lines.append(f"prompt-prune — {self.root}")
        lines.append(
            f"{len(self.files)} instruction file(s), {len(self.units)} units, "
            f"~{self.estimated_tokens} tokens "
            f"({self.total_chars} chars)"
        )
        if not self.git_known:
            lines.append(
                "NOTE: not a git repository (or git unavailable) — provenance "
                "unknown; age-based verdicts are skipped, not guessed."
            )
        counts = self.counts
        lines.append(
            "Verdicts: " + ", ".join(
                f"{k} {v}" for k, v in counts.items() if v or k == "KEEP"
            )
        )
        lines.append("")
        shown = [v for v in self.verdicts if v.verdict != "KEEP"]
        if not shown:
            lines.append("Nothing to prune. Every unit is recent, rationalised, "
                         "or unremarkable.")
            return "\n".join(lines)
        for v in shown:
            u = v.unit
            heading = " > ".join(u.heading_path) if u.heading_path else ""
            lines.append(
                f"[{v.verdict}] {u.id} (risk {v.risk})"
                + (f" — under '{heading}'" if heading else "")
            )
            lines.append(f"    {u.text.splitlines()[0][:120]}")
            for reason in v.reasons:
                lines.append(f"    - {reason}")
            prov = v.provenance
            if prov.known:
                when = prov.birth_date.date().isoformat() if prov.birth_date else "?"
                lines.append(
                    f"    born {prov.birth_short} by {prov.birth_author} "
                    f"on {when}"
                    + (f" — '{prov.birth_subject}'" if prov.birth_subject else "")
                    + f"; churn {prov.churn_commits} commit(s)"
                )
        lines.append("")
        kept_without_rationale = [
            v for v in self.verdicts
            if v.verdict == "KEEP" and not v.unit.rationale
        ]
        if not self.git_known:
            lines.append(
                "Rationale suggestions need git history — this is not a git "
                "repository, so no birth-commit subjects are available."
            )
        elif not kept_without_rationale:
            lines.append("All kept units already carry a rationale comment.")
        else:
            lines.append(
                "Suggested rationale comments for kept units without one "
                "(from their birth-commit subjects):"
            )
            for v in kept_without_rationale[:10]:
                subject = v.provenance.birth_subject
                if subject:
                    lines.append(
                        f"    {v.unit.id}: <!-- why: {subject} -->"
                    )
            if len(kept_without_rationale) > 10:
                lines.append("    ... (first 10 shown)")
        return "\n".join(lines)

    def to_json(self) -> str:
        def unit_json(u: Unit) -> dict:
            return {
                "id": u.id, "file": u.file,
                "start_line": u.start_line, "end_line": u.end_line,
                "kind": u.kind, "heading_path": list(u.heading_path),
                "text": u.text, "rationale": u.rationale,
            }

        def prov_json(p: Provenance) -> dict:
            return {
                "known": p.known,
                "birth_commit": p.birth_commit,
                "birth_author": p.birth_author,
                "birth_date": p.birth_date.isoformat() if p.birth_date else None,
                "birth_subject": p.birth_subject,
                "churn_commits": p.churn_commits,
                "commits_since_birth": p.commits_since_birth,
                "age_days": p.age_days,
            }

        return json.dumps({
            "root": self.root,
            "files": self.files,
            "unit_count": len(self.units),
            "estimated_tokens": self.estimated_tokens,
            "git_known": self.git_known,
            "counts": self.counts,
            "exit_code": self.exit_code,
            "verdicts": [
                {
                    "unit": unit_json(v.unit),
                    "provenance": prov_json(v.provenance),
                    "verdict": v.verdict,
                    "risk": v.risk,
                    "reasons": v.reasons,
                    "dead_refs": v.dead_refs,
                    "duplicate_of": v.duplicate_of,
                    "contradicts": v.contradicts,
                }
                for v in self.verdicts
            ],
        }, indent=2)
