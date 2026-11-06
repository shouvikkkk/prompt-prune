"""Risk scoring and prune verdicts.

The paper's formalism is the scoring model: deleting an instruction whose
rationale is gone costs O(2^|D|) in a prompt of |D| instructions, because
every other instruction is a candidate reason it exists; with a rationale
comment attached, deletion is O(1) — the comment says why it is there.
prompt-prune scores each unit's *deletion risk* from what is actually
observable, and assigns one verdict:

* ``PRUNE``   — safe to delete: the rule references something that no longer
  exists, or restates a newer unit, and it carries no rationale.
* ``REVIEW``  — probably stale (old, untouched since birth, no rationale)
  but the evidence is circumstantial; a human decides.
* ``CONFLICT``— contradicts another unit; deleting either side blindly is
  wrong. Needs a human, and the run fails (exit 2).
* ``KEEP``    — everything else: recent, maintained, rationalised, or
  simply unremarkable.

Scores are deliberately conservative: a unit is only PRUNE on hard
evidence (dead reference or near-duplicate of a newer unit), never on age
alone. The paper's own finding — older instructions are *less* likely to
be deleted — is treated as the trap it is, not as a signal of value.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .gitprov import Provenance
from .parse import Unit
from .refs import DeadRef
from .similarity import PairFinding

# A unit untouched for this many days with no rationale is stale enough to
# ask a human about. Churn of 1 (birth only) + age is the signature of a
# rule nobody has revisited since it was written.
STALE_DAYS = 180
# A unit shorter than this is usually a heading or a one-liner; length alone
# never prunes, but very long units cost context and are reported as bloat.
LONG_CHARS = 1200


@dataclass
class UnitVerdict:
    unit: Unit
    provenance: Provenance
    verdict: str  # PRUNE | REVIEW | CONFLICT | KEEP
    risk: int  # 0-100, higher = riskier to keep (for PRUNE) or to delete
    reasons: list[str] = field(default_factory=list)
    dead_refs: list[str] = field(default_factory=list)
    duplicate_of: str | None = None  # id of the newer unit it restates
    contradicts: str | None = None  # id of the unit it contradicts


def score_units(units: list[Unit], provenances: dict[str, Provenance],
                duplicates: list[PairFinding],
                contradictions: list[PairFinding],
                dead_refs: list[DeadRef]) -> list[UnitVerdict]:
    verdicts: dict[str, UnitVerdict] = {}
    for unit in units:
        prov = provenances.get(unit.id, Provenance())
        verdicts[unit.id] = UnitVerdict(
            unit=unit, provenance=prov, verdict="KEEP", risk=0,
        )

    # Dead references: the rule names something that no longer exists.
    for dead in dead_refs:
        v = verdicts[dead.unit.id]
        v.dead_refs.append(dead.reference)
        v.verdict = "PRUNE"
        v.reasons.append(f"references missing path `{dead.reference}`")
        v.risk = max(v.risk, 85)

    # Contradictions: neither side may be deleted blindly.
    for finding in contradictions:
        for unit in (finding.a, finding.b):
            v = verdicts[unit.id]
            v.verdict = "CONFLICT"
            v.contradicts = (
                finding.b.id if unit is finding.a else finding.a.id
            )
            v.reasons.append(f"contradicts {v.contradicts}: {finding.evidence}")
            v.risk = max(v.risk, 90)

    # Near-duplicates: the older copy is the prune candidate; the newer
    # copy (later birth, or later in the file when provenance is unknown)
    # is the one to keep.
    for finding in duplicates:
        va, vb = verdicts[finding.a.id], verdicts[finding.b.id]
        older, newer = _older_of(finding.a, finding.b, provenances)
        ov, nv = verdicts[older.id], verdicts[newer.id]
        if ov.verdict != "CONFLICT":
            ov.verdict = "PRUNE"
            ov.duplicate_of = newer.id
            ov.reasons.append(
                f"restates {newer.id} ({finding.evidence})"
            )
            ov.risk = max(ov.risk, 80)
        if nv.verdict == "KEEP":
            nv.reasons.append(f"kept over duplicate {older.id}")

    # Staleness: old, untouched since birth, no rationale comment.
    for unit in units:
        v = verdicts[unit.id]
        if v.verdict in ("CONFLICT", "PRUNE"):
            continue
        prov = v.provenance
        age = prov.age_days
        if (age is not None and age >= STALE_DAYS
                and prov.churn_commits <= 1 and not unit.rationale):
            v.verdict = "REVIEW"
            v.reasons.append(
                f"untouched since birth {prov.birth_short or ''} "
                f"({age} days ago) with no rationale comment"
            )
            v.risk = max(v.risk, 55)
        elif unit.rationale:
            v.reasons.append("has a rationale comment — deletion is cheap (O(1))")
        if len(unit.text) >= LONG_CHARS and v.verdict == "KEEP":
            v.reasons.append(
                f"long unit ({len(unit.text)} chars) — costs context every session"
            )
            v.risk = max(v.risk, 20)

    return [verdicts[unit.id] for unit in units]


def _older_of(a: Unit, b: Unit, provenances: dict[str, Provenance]) -> tuple[Unit, Unit]:
    """Return (older, newer) of two units by birth date, falling back to
    file order when provenance is unknown for either side."""
    pa, pb = provenances.get(a.id), provenances.get(b.id)
    if pa and pb and pa.birth_date and pb.birth_date:
        return (a, b) if pa.birth_date <= pb.birth_date else (b, a)
    # Fall back to position: the later unit in the file is the restatement.
    return (a, b) if (a.file, a.start_line) <= (b.file, b.start_line) else (b, a)
