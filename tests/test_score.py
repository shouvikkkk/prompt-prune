"""Tests for promptprune.score — verdicts."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from promptprune.gitprov import Provenance  # noqa: E402
from promptprune.parse import Unit  # noqa: E402
from promptprune.refs import DeadRef  # noqa: E402
from promptprune.score import score_units  # noqa: E402
from promptprune.similarity import PairFinding  # noqa: E402


def _unit(text: str, line: int, rationale: str | None = None) -> Unit:
    return Unit(id=f"CLAUDE.md:{line}", file="CLAUDE.md",
                start_line=line, end_line=line, kind="bullet", text=text,
                rationale=rationale)


def _old_prov(days: int = 300) -> Provenance:
    return Provenance(
        known=True, birth_commit="a" * 40, birth_short="aaaaaaa",
        birth_author="Dev", birth_date=datetime.now(timezone.utc) - timedelta(days=days),
        birth_subject="Old rule", churn_commits=1, commits_since_birth=200,
    )


def test_dead_ref_is_prune():
    unit = _unit("Run `scripts/gone.sh` before deploy.", 1)
    verdicts = score_units([unit], {}, [], [],
                           [DeadRef(unit=unit, reference="scripts/gone.sh", kind="file")])
    assert verdicts[0].verdict == "PRUNE"
    assert "scripts/gone.sh" in verdicts[0].dead_refs


def test_contradiction_beats_everything():
    a = _unit("Always run the full test suite before committing.", 1)
    b = _unit("Never run the full test suite before committing.", 2)
    finding = PairFinding(kind="CONTRADICTION", a=a, b=b, score=3.0,
                          evidence="shared subject: test suite")
    verdicts = score_units([a, b], {}, [], [finding], [])
    assert {v.verdict for v in verdicts} == {"CONFLICT"}


def test_old_untouched_unit_without_rationale_is_review():
    unit = _unit("Prefer tabs in Makefiles.", 1)
    verdicts = score_units([unit], {unit.id: _old_prov()}, [], [], [])
    assert verdicts[0].verdict == "REVIEW"


def test_old_unit_with_rationale_stays_keep():
    unit = _unit("Prefer tabs in Makefiles.", 1, rationale="make requires tabs")
    verdicts = score_units([unit], {unit.id: _old_prov()}, [], [], [])
    assert verdicts[0].verdict == "KEEP"


def test_recent_unit_stays_keep():
    unit = _unit("Prefer tabs in Makefiles.", 1)
    fresh = Provenance(known=True, birth_commit="b" * 40, birth_short="bbbbbbb",
                       birth_author="Dev",
                       birth_date=datetime.now(timezone.utc) - timedelta(days=3),
                       birth_subject="New rule", churn_commits=1)
    verdicts = score_units([unit], {unit.id: fresh}, [], [], [])
    assert verdicts[0].verdict == "KEEP"


def test_older_duplicate_is_prune_newer_kept():
    a = _unit("Always run the full test suite before committing changes.", 1)
    b = _unit("Always run the full test suite before you commit any changes.", 2)
    finding = PairFinding(kind="NEAR-DUPLICATE", a=a, b=b, score=0.9,
                          evidence="shared terms: test, suite")
    old = _old_prov(days=300)
    fresh = Provenance(known=True, birth_commit="c" * 40, birth_short="ccccccc",
                       birth_author="Dev",
                       birth_date=datetime.now(timezone.utc) - timedelta(days=2),
                       birth_subject="Restated rule", churn_commits=1)
    verdicts = score_units([a, b], {a.id: old, b.id: fresh}, [finding], [], [])
    by_id = {v.unit.id: v for v in verdicts}
    assert by_id[a.id].verdict == "PRUNE"
    assert by_id[a.id].duplicate_of == b.id
    assert by_id[b.id].verdict == "KEEP"
