"""prompt-prune — a provenance-aware pruner for agent instruction files.

Agent instruction files (CLAUDE.md, AGENTS.md, ...) only ever grow: appending
an instruction is cheap, but deleting one whose rationale is gone risks a
correctness regression. Chakrabarti (arXiv:2608.11095, Aug 2026) measured this
across 247,694 instruction lifetimes in 1,867 repos: prompts more than triple
(+226%), gaining +4.9 net instructions per commit, and the older an
instruction gets, the less likely it is to be deleted.

prompt-prune connects each instruction to the git commit that introduced it,
its author and date, and whether the code, file or command it references
still exists — so a maintainer can tell which rules are safe to delete.
"""

__version__ = "0.1.0"
