"""Near-duplicate and contradiction detection between instruction units.

Two failure modes the paper's data implies but no linter catches:

* **Near-duplicates** — the same rule restated in two places. One copy gets
  updated, the other rots, and the agent follows whichever it reads first.
  Detected with a token-set Jaccard plus a difflib ratio on normalized text.

* **Contradictions** — two units that direct opposite behaviour on the same
  subject ("Always run the full test suite" vs "Never run the full test
  suite before committing"). Detected conservatively: the pair must share
  at least two content words, one side must carry a strong negation marker,
  and the other a positive directive marker. This deliberately under-flags
  rather than crying wolf on scoped rules ("never in CI, always locally"
  still needs a human, so it is flagged only when neither side states a
  scope word).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .parse import Unit

STOPWORDS = frozenset("""
a an the and or of to in on for with by at as is are was were be been being
it its this that these those you your we our they their he she his her
from into over under after before between through during without within
not no nor but if then else when while can could should would may might
will shall do does did done have has had having use uses used using
""".split())

NEGATION_MARKERS = (
    "never", "do not", "don't", "dont", "must not", "mustn't", "avoid",
    "forbidden", "prohibited", "not allowed", "disallow", "ban", "banned",
    "refuse", "reject", "no ", "don't ever",
)
POSITIVE_MARKERS = (
    "always", "must", "should", "prefer", "use ", "do ", "only ", "ensure",
    "require", "required", "mandatory",
)
# Words that scope a rule to a context — when the two sides mention
# *different* scope words, the pair may be complementary rather than
# contradictory, so we stay silent. Deliberately narrow: generic words
# like "test" or "commit" appear in ordinary instructions and would
# suppress real contradictions.
SCOPE_WORDS = frozenset("""
ci local locally production development staging debug release
windows linux macos mac docker container pr merge branch main
hotfix emergency remote
""".split())

DEFAULT_JACCARD = 0.70
DEFAULT_RATIO = 0.80


@dataclass
class PairFinding:
    kind: str  # "NEAR-DUPLICATE" | "CONTRADICTION"
    a: Unit
    b: Unit
    score: float  # similarity for duplicates; shared-word count for contradictions
    evidence: str


def _content_words(unit: Unit) -> set[str]:
    # Strip trailing dots left by sentence punctuation ("committing.")
    # while keeping path dots inside words (src/foo.py stays intact).
    return {
        w.rstrip(".") for w in unit.words
        if w.rstrip(".") not in STOPWORDS and len(w.rstrip(".")) > 2
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_near_duplicates(units: list[Unit], min_jaccard: float = DEFAULT_JACCARD,
                         min_ratio: float = DEFAULT_RATIO) -> list[PairFinding]:
    findings: list[PairFinding] = []
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            a, b = units[i], units[j]
            wa, wb = _content_words(a), _content_words(b)
            if len(wa) < 3 or len(wb) < 3:
                continue
            jac = _jaccard(wa, wb)
            ratio = difflib.SequenceMatcher(None, a.normalized, b.normalized).ratio()
            if jac >= min_jaccard or ratio >= min_ratio:
                score = max(jac, ratio)
                shared = sorted(wa & wb)[:6]
                findings.append(PairFinding(
                    kind="NEAR-DUPLICATE",
                    a=a, b=b, score=round(score, 2),
                    evidence=f"shared terms: {', '.join(shared)}"
                    + (f"; text similarity {ratio:.2f}" if ratio >= min_ratio else ""),
                ))
    return findings


def _has_marker(text: str, markers: tuple[str, ...]) -> str | None:
    lowered = f" {text} "
    for marker in markers:
        if marker in lowered:
            return marker
    return None


def find_contradictions(units: list[Unit]) -> list[PairFinding]:
    findings: list[PairFinding] = []
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            a, b = units[i], units[j]
            wa, wb = _content_words(a), _content_words(b)
            shared = wa & wb
            if len(shared) < 2:
                continue
            # Scoped rules may legitimately differ per context.
            raw_a = {w.rstrip(".") for w in a.words}
            raw_b = {w.rstrip(".") for w in b.words}
            if (raw_a | raw_b) & SCOPE_WORDS and _scope_differs(a, b):
                continue
            na, nb = a.normalized, b.normalized
            neg_a = _has_marker(na, NEGATION_MARKERS)
            neg_b = _has_marker(nb, NEGATION_MARKERS)
            pos_a = _has_marker(na, POSITIVE_MARKERS)
            pos_b = _has_marker(nb, POSITIVE_MARKERS)
            # One side negates, the other directs — on the same subject.
            if (neg_a and pos_b) or (neg_b and pos_a):
                findings.append(PairFinding(
                    kind="CONTRADICTION",
                    a=a, b=b, score=float(len(shared)),
                    evidence=(
                        f"shared subject: {', '.join(sorted(shared)[:5])}; "
                        f"'{neg_a or neg_b}' vs '{pos_a or pos_b}'"
                    ),
                ))
    return findings


def _scope_differs(a: Unit, b: Unit) -> bool:
    """True when the two units mention *different* scope words.

    Uses the raw word set (no length filter): scope words like "ci" are
    two letters and would otherwise be dropped by _content_words.
    """
    sa = {w.rstrip(".") for w in a.words} & SCOPE_WORDS
    sb = {w.rstrip(".") for w in b.words} & SCOPE_WORDS
    return bool(sa and sb and sa != sb)
