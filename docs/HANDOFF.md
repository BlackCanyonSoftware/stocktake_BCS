# StockTake: handoff

## Current state
Planning only. **No code exists yet.** The repository holds the MIT `LICENSE` it was created with and the planning documents written in session 1. The next session writes Milestone 0.

Nothing is committed to the remote by this work — commits are local, for review and pushing by the owner.

## What this project is
A dependency checker that drops into a project's own test suite: it reads what the project pins, asks the public registries for newer versions and known advisories, and fails the tests only on something actually unsafe. Never edits a file. See [PRD.md](PRD.md) for the full statement and [ARCHITECTURE.md](ARCHITECTURE.md) for the shape.

It is a generalisation of `modules/depcheck` in the author's `ai-suite` repository (on KPrime at `/home/kyle1/ai-suite`), which works, has 33 passing tests and is the reference implementation to port from. **That repository is deliberately not being modified by this project** — it stays as the working reference until StockTake is proven.

## Decisions already made (do not relitigate without an ADR)
- Python 3.11+, standard library only at runtime — [ADR 0001](adr/0001-python-with-a-standard-library-only-core.md)
- `.stocktake.toml` at the project root holds config and policy; TOML, not YAML — [ADR 0002](adr/0002-one-toml-config-file-at-the-project-root.md)
- Readers and registry clients are separate narrow interfaces, one file per ecosystem, each with a guard test — [ADR 0003](adr/0003-readers-and-registry-clients-as-separate-interfaces.md)
- Only vulnerable, withdrawn and expired-policy findings fail; outdated warns — [ADR 0004](adr/0004-only-unsafe-findings-fail-the-build.md)
- Installed package and pytest plugin is the primary path; a generated single-file copy is the fallback — [ADR 0005](adr/0005-installed-package-plus-a-generated-single-file-copy.md)
- Scope confirmed by the owner on 2026-10-29: Python + npm + GitHub Actions + container tags for v1; MIT licence; package plus vendor command; leave `ai-suite` alone.

## Work in progress
None. Session 1 ended at the approval pause after the plan, per the house workflow.

## Next steps
1. **Milestone 0** ([ROADMAP.md](ROADMAP.md)): repo foundation, then port the core from `ai-suite/modules/depcheck/__init__.py` split along the module boundaries in ARCHITECTURE.md, with its 33 tests adapted and green.
2. Milestone 1: `.stocktake.toml` loader, drop the hard-coded exclusion list, formalise the `Reader` protocol, add the `requirements*.txt` and lockfile readers.
3. Milestone 2: the pytest plugin, so a project adds the check in one step.

## Where the source to port from lives
On KPrime, in `/home/kyle1/ai-suite`. Use `bash ~/.claude/bin/kp '<command>'` to run anything there; never hand-quote through `ssh`. The five files that matter:

| File | Lines | What it becomes |
|---|---|---|
| `modules/depcheck/__init__.py` | 505 | `src/stocktake/` split into `models`, `versions`, `scan`, `readers/`, `registries/`, `policy`, `evaluate`, `report/` |
| `tests/test_dependencies.py` | 350 | `tests/`, split to mirror the modules; the `FakeNet` fake carries over nearly unchanged |
| `scripts/canai-deps` | 19 | `src/stocktake/cli.py` plus the console-script entry point |
| `config/deps-policy.yaml` | 13 | the `[policy]` tables in `.stocktake.toml` |
| `docs/dependencies.md` | 37 | `README.md` and `docs/` |

A copy of all five was pulled into the session scratchpad during session 1; it is not in the repository and is not meant to be.

## Gotchas and things learned the hard way
These come from the first real run of the original and should not be rediscovered:
- **Raw advisory lists are unreadable.** One package returned 90 OSV entries. Merge aliases, show the worst five with a count of the rest, name the one version that clears them all.
- **The scanner will miss pins unless a test counts them independently.** `uv tool install maigret==0.6.6` was invisible until a guard test compared a plain regular-expression count with what the scanner found. Every reader needs this test.
- **Not every GitHub release tag is a version.** Projects park model files and assets under `v0.0.0`, which produced a false "major update available". It is ignored.
- **A registry timeout is `unknown`, never clean.** Getting this wrong turns a network blip into a false all-clear.
- **Writing the exclusion list into the source is what made the original un-reusable.** It still contains paths that exist in only one repository.
- **`packaging` may be absent.** Version comparison needs its fallback, and the fallback needs test cases.

## Candidate projects to test against (M5)
- `ai-suite` on KPrime — the reference; Dockerfile pip pins, GitHub release downloads, `pyproject.toml` dev dependencies.
- `Documents/Brand Logos` (brand kit) — a real Python project with pytest, pre-commit, Dependabot and `.github/workflows`, so it exercises the workflow reader and gives a direct comparison against Dependabot's findings.
- A Node project, for the npm reader. None identified yet — pick one in M3.

## Open questions for the owner
Listed in [PRD.md](PRD.md) under "Open questions". None of them block Milestone 0.

## Session log
### Session 1 — 2026-10-29
Read the writeup and the house project standards; pulled the five reference files from `ai-suite` on KPrime into the scratchpad; confirmed four scope decisions with the owner; wrote `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/DESIGN.md` and ADRs 0001–0005; committed locally. Stopped at the approval pause before any code, per the workflow. Verified: the GitHub repository already exists, is public and carries an MIT licence; the name `stocktake` is unclaimed on PyPI as of this date. No code was written, so nothing is tested.
