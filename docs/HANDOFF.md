# StockTake: handoff

## Current state
**Milestone 0 is done and verified.** The tool installs, runs against a real project and prints a correct report, with 148 passing tests, clean lint and clean strict type checking. The next session starts Milestone 1.

Commits are local only. Nothing has been pushed; CI has therefore never run and is **not verified**.

```bash
py -3.11 -m venv .venv
./.venv/Scripts/python -m pip install -e ".[dev]"   # .venv/bin/python on macOS and Linux
./.venv/Scripts/python -m pytest                    # 148 tests, ~1.5s
./.venv/Scripts/python -m stocktake                 # check this project itself
```

## What this project is
A dependency checker that drops into a project's own test suite: it reads what the project pins, asks the public registries for newer versions and known advisories, and fails the tests only on something actually unsafe. Never edits a file. See [PRD.md](PRD.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

It is a generalisation of `modules/depcheck` in the author's `ai-suite` repository (on KPrime at `/home/kyle1/ai-suite`). **That repository is deliberately untouched** and stays the reference implementation until StockTake is proven.

## Decisions already made (do not relitigate without an ADR)
- Python 3.11+, standard library only at runtime — [ADR 0001](adr/0001-python-with-a-standard-library-only-core.md). A guard test enforces it.
- `.stocktake.toml` at the project root holds config and policy; TOML, not YAML — [ADR 0002](adr/0002-one-toml-config-file-at-the-project-root.md)
- Readers and registry clients are separate narrow interfaces, one module per ecosystem, each with a guard test — [ADR 0003](adr/0003-readers-and-registry-clients-as-separate-interfaces.md)
- Only vulnerable, withdrawn and expired-policy findings fail; outdated warns — [ADR 0004](adr/0004-only-unsafe-findings-fail-the-build.md)
- Installed package and pytest plugin is the primary path; a generated single-file copy is the fallback — [ADR 0005](adr/0005-installed-package-plus-a-generated-single-file-copy.md)
- Scope confirmed by the owner on 2026-10-29: Python + npm + GitHub Actions + container tags for v1; MIT licence; package plus vendor command; leave `ai-suite` alone.

## Work in progress
None. M0 is complete; M1 has not been started.

## Next steps
1. **Milestone 1** ([ROADMAP.md](ROADMAP.md)): make `ecosystems` and `cache.ttl_hours` configurable, have the CLI pass `groups` through to `scan()`, let a project acknowledge an unread manifest in config, and add the `requirements*.txt` and lockfile readers.
2. Milestone 2: the pytest plugin, so a project adds the check in one step. This is the milestone that makes the tool actually adoptable across the author's repositories.
3. Milestone 5 is where the ten repositories the owner mentioned get used. Start that list now (see below) — false positives found in real use are worth more than any amount of design.

## How M0 was verified, and what that did not cover
- 148 tests pass, including the one marked `network` that asks the real registries about this project's own dependencies.
- `ruff check`, `ruff format --check` and `mypy` (strict, on `src`) are clean.
- **The port is exact.** The scanner was run against `ai-suite`'s real `docker/dev/Dockerfile`, `docker/llama-swap/Dockerfile` and `pyproject.toml`, and compared against the original scanner's output on the same files: 40 dependencies, identical names, versions, source locations and specifiers, no differences at all. The comparison script is in the session scratchpad, not the repository.
- A real run against a project pinning `pillow==9.0.0` and `requests==2.19.1` found 52 and 5 advisories respectively and named `13.0.0` and `2.33.0` as the versions that clear them — matching what the original writeup reported for Pillow.
- **Not covered:** CI (never pushed), Linux and macOS (only Windows was run locally; CI covers Linux), Python 3.12 and 3.13 (only 3.11 was run locally), and any project that is not Python.

## Where the source to port from lives
On KPrime, in `/home/kyle1/ai-suite`. Use `bash ~/.claude/bin/kp '<command>'` to run anything there, and `kpf` for a script; never hand-quote through `ssh`. Still unported, for later milestones:

| File | What is left to take from it |
|---|---|
| `config/deps-policy.yaml` | the three live policy entries, when that repo is switched over |
| `docs/dependencies.md` | nothing; its content is in README.md now |

## Gotchas and things learned the hard way
These come from the original's first real run and from building M0. None should be rediscovered.
- **Raw advisory lists are unreadable.** One package returned 52 OSV entries in testing here, and 90 in the original. Merge aliases, show the worst five with a count of the rest, name the one version that clears them all.
- **The scanner will miss pins unless a test counts them independently.** `uv tool install maigret==0.6.6` was invisible in the original until a guard test compared a plain regex count with what the scanner found. Every new reader needs that test; `tests/test_readers_dockerfile.py` has the pattern.
- **Not every GitHub release tag is a version.** Projects park model files under `v0.0.0`, which produced a false "major update available". It is skipped, with a test.
- **A registry timeout is `unknown`, never clean.** Offline means *every* lookup failed; one failure is that one name's problem, not the run's.
- **Writing the exclusion list into the source is what made the original un-reusable.** It still contains paths that exist in only one repository. `DEFAULT_EXCLUDES` is generic and anything project-specific goes in that project's config.
- **`packaging` may be absent.** Version comparison needs its fallback, and the fallback needs test cases.
- **`ruff format` reformats Python code blocks inside Markdown.** It rewrote snippets in `ARCHITECTURE.md` and ADR 0003 on the first run; `extend-exclude = ["*.md"]` now stops it.
- **The scanner is faithful to shell semantics, which can look like a bug.** A test fixture written with a literal `\n` in a `RUN` line produced findings for a package called `n` — correctly, because `pip install \n pillow==9.0.0` really does ask for a package called `n` in a shell. Check the fixture before the code.
- **`uv` and `pre-commit` are not installed on the development machine.** Use `py -3.11 -m venv` and `pip install -e`. Do not install tools there without asking.

## Projects to try it on (M5)
The owner has about ten repositories available for this, and the list is the most valuable thing M5 can have. Known so far:
- `ai-suite` on KPrime — the reference. Dockerfile pip pins, GitHub release downloads, `pyproject.toml` dev dependencies. Already compared against, scanner-only.
- `Documents/Brand Logos` (the brand kit) — a real Python project with pytest, pre-commit, Dependabot and `.github/workflows`, so it exercises the workflow reader when M3 lands and gives a direct comparison against what Dependabot reports.
- A Node project, for the npm reader in M3. Not identified yet.
- **Ask the owner for the remaining names and note them here.**

## Open questions for the owner
In [PRD.md](PRD.md) under "Open questions". None block M1. The one worth deciding soonest: whether to publish `stocktake` to PyPI now (the name is free as of 2026-10-29) or wait until there are two real consumers.

## Session log
### Session 2 — 2026-10-30
Built Milestone 0: repo foundation (`pyproject.toml`, ruff, mypy, pytest, CI workflow, ignore and editor files), the core ported from `ai-suite/modules/depcheck/__init__.py` and split into 20 modules along the boundaries in ARCHITECTURE.md, 148 tests, README, and three documentation corrections where the code ended up differing from the plan (`--config` not `--policy`, exit code 2's meaning, the real `Reader` shape). Verified as described above. Committed locally; not pushed.

### Session 1 — 2026-10-29
Read the writeup and the house project standards; pulled the five reference files from `ai-suite` on KPrime into the scratchpad; confirmed four scope decisions with the owner; wrote `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/DESIGN.md` and ADRs 0001–0005; committed locally. Stopped at the approval pause before any code, per the workflow. No code was written, so nothing was tested.
