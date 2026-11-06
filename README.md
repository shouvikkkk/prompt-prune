# prompt-prune

**A provenance-aware pruner for agent instruction files** — find the rules in
your `CLAUDE.md` / `AGENTS.md` that are safe to delete, contradict each
other, or reference things that no longer exist.

## The problem

Agent instruction files only ever grow. Appending a rule is cheap, but
deleting one whose rationale is gone risks a correctness regression — so
nobody deletes anything, and the file bloats past the point where
instruction-following measurably degrades.

Chakrabarti measured this across 247,694 instruction lifetimes in 1,867
repositories (*"Why Does CLAUDE.md Keep Growing? Catastrophic Remembering
in Agentic Coding"*, arXiv:2608.11095, Aug 2026):

> "grow without bound in real repositories, stopping only when the
> repository retires"

Prompts more than triple over their lifetime (+226%), gaining +4.9 net
instructions per commit — and the older an instruction gets, the *less*
likely it is to be deleted. The paper's formalism is the key: deleting an
instruction whose rationale is gone costs O(2^|D|) in a prompt of |D|
instructions, because every other instruction is a candidate reason it
exists. With a rationale comment attached, deletion is O(1) — the comment
says why it is there.

The paper only proposes a *practice* (write `<!-- why: … -->` comments).
There is no tool. This is the tool.

## What it does

`prompt-prune check <path>` audits every instruction file under a repo
(`CLAUDE.md`, `AGENTS.md`, `copilot-instructions.md`, `GEMINI.md`,
`MUSE.md`, `.cursor/rules/*.md`, `.claude/*.md`,
`.github/copilot-instructions.md`) and reports, per instruction:

- **Provenance** — the git commit that introduced the rule's current
  wording, its author, date, and commit message, plus churn (how many
  commits have touched it). The birth-commit subject doubles as a
  suggested `<!-- why: … -->` rationale comment.
- **Near-duplicates** — the same rule restated in two places (one copy
  gets updated, the other rots). The older copy is the prune candidate.
- **Contradictions** — two rules directing opposite behaviour on the same
  subject. Scoped rules ("never in CI, always locally") are not flagged.
- **Dead references** — a rule naming a file or directory that no longer
  exists (`scripts/migrate.sh` was deleted; the rule still demands it).
- **Staleness** — a rule untouched since birth, 180+ days old, with no
  rationale comment. Circumstantial evidence only: reported as REVIEW,
  never auto-PRUNE.

## Verdicts and exit codes

| Verdict | Meaning | Exit |
|---|---|---|
| `PRUNE` | Safe to delete: dead reference, or restates a newer unit | 1 |
| `REVIEW` | Probably stale (old, untouched, no rationale) — a human decides | 1 |
| `CONFLICT` | Contradicts another unit; deleting either side blindly is wrong | 2 |
| `KEEP` | Recent, maintained, rationalised, or unremarkable | 0 |

Exit 3 means no instruction files were found, or the path is not a
directory. When the target is not a git repository, provenance is reported
as unknown and age-based verdicts are skipped — never guessed.

## Install

```bash
pip install prompt-prune
```

Requires Python 3.10+ and `git` on `PATH` (for provenance only; the audit
still runs without git). No third-party dependencies — stdlib only.

## Usage

```bash
prompt-prune check .                      # text report, exit code by verdict
prompt-prune check . --format json        # machine-readable report
prompt-prune check . --min-similarity 0.8 # stricter duplicate threshold
prompt-prune check . --no-git             # skip git provenance
```

## Demo

```bash
$ prompt-prune check examples/bloated
prompt-prune — examples/bloated
1 instruction file(s), 9 units, ~108 tokens (435 chars)
NOTE: not a git repository (or git unavailable) — provenance unknown; age-based verdicts are skipped, not guessed.
Verdicts: KEEP 4, PRUNE 2, CONFLICT 3

[CONFLICT] CLAUDE.md:5 (risk 90)
    - Always run the full test suite before committing changes.
    - contradicts CLAUDE.md:7: shared subject: committing, full, run, suite, test; 'never' vs 'always'
[CONFLICT] CLAUDE.md:7 (risk 90)
    - Never run the full test suite before committing.
    - contradicts CLAUDE.md:5: shared subject: committing, full, run, suite, test; 'never' vs 'always'
[PRUNE] CLAUDE.md:11 (risk 85)
    - Run `scripts/migrate.sh` before every deploy.
    - references missing path `scripts/migrate.sh`
[PRUNE] CLAUDE.md:19 (risk 80)
    - Use spaces for indentation in Python files.
    - restates CLAUDE.md:20 (shared terms: files, indentation, python, spaces; text similarity 0.91)
```

The clean example exits 0:

```bash
$ prompt-prune check examples/clean
prompt-prune — examples/clean
1 instruction file(s), 2 units, ~27 tokens (110 chars)
Verdicts: KEEP 2

Nothing to prune. Every unit is recent, rationalised, or unremarkable.
```

## How it differs

- **Markdown linters / the SCAM-2026 "configuration smells" study** can
  flag a file as bloated (>200 lines) but cannot say *which* rule is safe
  to delete — they have no provenance. prompt-prune connects each rule to
  the commit that introduced it.
- **Skill-audit tools** (skills-check, skillbound, skillclash) audit
  *skills* — their promises, conflicts, and clones. prompt-prune audits
  *instruction files* — the prose every agent in the repo actually reads —
  and the failure mode is different: unbounded growth with decayed
  rationale, not malicious content.
- **The paper's own proposal** is a writing practice. prompt-prune is the
  enforcement: it finds the rules that already lost their rationale and
  suggests the comment from the birth commit's own message.

## Honest limitations

- **Blame birth ≠ original intent.** `git blame` dates the current
  wording, not the first time the idea appeared; a reworded rule looks
  younger than it is. The report shows the birth-commit subject so you
  can judge.
- **Contradiction detection is heuristic.** It needs shared content words
  plus opposing polarity markers, and it deliberately under-flags rather
  than crying wolf. Real contradictions phrased without "always/never"
  markers will be missed.
- **Dead-reference checks are path-only.** A rule naming a removed
  command, flag, or API is not flagged unless it looks like a file path.
- **No live-Claude-Code verification.** The tool was validated on
  synthetic repos and real git history, not against a running Claude Code
  session's instruction-following behaviour.
- **No network features.** It audits local trees only; it does not fetch
  remote instruction files or compare against upstream.

## Development

```bash
python -m pytest tests/   # 34 tests, stdlib only
```
