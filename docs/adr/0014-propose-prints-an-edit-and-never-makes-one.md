# ADR 0014: `propose` prints an edit and never makes one — and often the edit is not the answer

- **Date:** 2026-11-12
- **Status:** accepted
- **Rests on:** [ADR 0004](0004-only-unsafe-findings-fail-the-build.md), [ADR 0008](0008-a-tag-its-publisher-moves-is-a-range.md)

## Context
The report says a dependency is vulnerable, names the version that clears it, and stops. The next thing anybody does is open the file and work out what to type. `propose` does that part: for every finding worth acting on, the exact change, where.

Two things make it more than a formatting job.

**The first is the rule it lives under.** `AGENTS.md`: *it never edits a dependency, with any flag, ever; the furthest it may go is printing the edit it would make.* That is not timidity. A tool that both finds problems and fixes them has to be trusted twice, and the second trust is much more expensive to earn — a wrong upgrade applied silently across a repository is a worse day than any missed advisory. Printing is also what makes the output reviewable: a diff somebody reads before pasting is a diff somebody can reject.

**The second is that an edit is frequently the wrong answer.** The roadmap framed the hard part as "what is the right target version", and `advisories.fix_target` already answered that. The real difficulty is that the same finding wants a different action depending on which kind of file it came from, and a tool printing `- old / + new` for all of them would confidently tell people to hand-edit generated files.

## Three kinds of file, three kinds of answer

| Where the version lives | What the project should do | What `propose` prints |
|---|---|---|
| Written by hand: a `requirements.txt` pin, a Dockerfile `FROM` or `pip install`, a workflow `uses:`, a pre-commit `rev` | Edit that line | the line as it stands and as it would be |
| A generated lock: `package-lock.json`, `pnpm-lock.yaml`, `uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile.lock` | Run the tool that regenerates it | `$ npm install lodash@4.17.21`, `$ uv lock --upgrade-package pillow`, … |
| A range resolved against what is installed: `pyproject.toml` saying `pillow>=8` | Upgrade the environment; the file is not wrong | `$ pip install --upgrade "pillow==10.0.0"` |

The middle row is the one worth being emphatic about. A hand-edited lock file is a lock that disagrees with itself: the version changes and the integrity hash, the resolved URL and the dependency tree below it do not. Printing a tempting `- "version": "4.17.15"` would produce exactly that, and it would look authoritative while doing it.

## Options considered

**A. Print a patch for everything, including locks.** One code path, uniform output, and it teaches people to corrupt their lock files.

**B. Print only the target version and let the reader find it.** What the report already does. No new wrongness and no new help.

**C. Three kinds, chosen by where the version actually lives.** Taken.

**D. Write the files, behind `--fix`.** Rejected by a rule that predates this record, and the rule is right. It is also the one feature that would make StockTake unsafe to run unattended, which is the property two trial reports were spent establishing.

## Decision
Option C, with one safety property doing most of the work.

**An edit is offered only when the old version is found exactly once on its line.** The token looked for is the longest one that identifies the dependency — `pillow==9.0.0` before `==9.0.0` — so a second package pinned at the same version on the same `RUN pip install` line cannot be hit by mistake. Found twice, or not at all, and no edit is printed: the proposal falls back to a command or to a sentence. *An edit that is nearly right is worse than a sentence saying what to do*, because the whole value here is that it can be pasted without being checked twice.

The rest:

- **A moving tag is cut back to the precision the project wrote.** Somebody on `python:3.12` is told `3.15`, not `3.15.2`; somebody on `actions/checkout@v2` is told `@v7`, not `@v7.0.1`. They are choosing to follow a line, and the publisher keeps that tag pointing at the newest of it ([ADR 0008](0008-a-tag-its-publisher-moves-is-a-range.md)). This is the one place the *written* form matters more than the resolved one, because the output is literally the text to type.
- **A vulnerability with no published fix gets a sentence, not a guess.** "No fixed version is named by any of its advisories" is the honest answer and a real decision for a person.
- **Links only where they cannot be wrong.** PyPI and npm have a stable per-version URL. GitHub gets its releases page rather than the compare link that would be far more useful, because the registry strips the `v` from a tag and the original text is not recoverable — a 404 is worse than no link. Container images get none: the page depends on which registry answered.
- **It is a `--format`, not a subcommand.** A proposal is another rendering of a run, so it inherits `--root`, `--config`, `--only` and everything else rather than growing a second copy of them. `--only vulnerable --format propose` is the useful pairing.
- **The vocabulary is in `models.py`.** `propose.py` opens project files to quote a line; `report/propose.py` opens nothing. Both need `Proposal`, and neither imports the other, so the type lives where everything else that depends on nothing lives.

## Consequences
- **Good.** The output is paste-ready for the common case and refuses to be paste-ready for the cases where pasting is wrong.
- **Good.** It needed no new reader, no new registry client and no new network traffic: it is a second reading of what a run already found, plus the source lines.
- **Good.** The three kinds are a better description of the problem than the roadmap's framing was, and they will survive the next ecosystem — a new reader lands in one of the three by where its versions live.
- **Cost.** `propose.py` re-opens project files that `scan` has already read, and reads them a second time at a different layer. Cheap (one read per file, remembered) but it is a second place that knows a project file can be opened, and the boundary that keeps `report/` pure is now a boundary somebody has to hold rather than one the structure enforces.
- **Cost.** The edit is textual, not syntactic. It rewrites a line, so it is correct for the formats here — all of which put a version on one line — and would be wrong for a format that spread one across several. A reader whose versions do not sit on a single line needs thinking about, not just adding.
- **Cost.** `python:3.15-slim` is proposed on the strength of the tag listing containing `3.15`, which it does; but the general claim that a truncated moving tag exists is a convention, not a guarantee. A publisher who ships `3.15.2` and no `3.15` would get a proposal naming a tag that does not exist. The alternative — proposing the full version — is wrong far more often, for everyone who deliberately tracks a line.
- **Cost.** Nothing verifies a proposal against the registry: it is not asked whether `pillow==10.0.0` is a real release, only told so by the advisory data. The fix target comes from the advisory's own `fixed` list, so it is as good as that data and no better.
