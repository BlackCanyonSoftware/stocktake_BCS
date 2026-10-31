# AGENTS.md

Guide for AI coding assistants working on StockTake. Read [docs/HANDOFF.md](docs/HANDOFF.md) first: it says where things stand, and it carries the traps that have already cost somebody time.

## What this is

A dependency checker that drops into a project's own test suite. It reads what the project pins, asks the public registries whether a newer release exists and whether the pinned one has a known advisory, and fails only when something is actually unsafe. It never edits a file and never needs an account.

**Rigor tier: MVP.** Python 3.11+, no runtime dependencies at all.

## Commands

```bash
./.venv/Scripts/python -m pytest              # whole suite, incl. the live check (528 tests, ~6s)
./.venv/Scripts/python -m pytest -m "not network"
./.venv/Scripts/python -m ruff check .
./.venv/Scripts/python -m ruff format .
./.venv/Scripts/python -m mypy                # strict, over src
./.venv/Scripts/python -m stocktake           # run it against itself
./.venv/Scripts/stocktake vendor vendored/    # AFTER ANY CHANGE TO src/stocktake/
```

Setup: `py -3.11 -m venv .venv && ./.venv/Scripts/python -m pip install -e ".[dev]"`. Use `./.venv/Scripts/python` on Windows, `.venv/bin/python` elsewhere.

## Project map

```
src/stocktake/
  models.py        the vocabulary: Dep, Advisory, Finding, Report, Unread, Unreadable. Depends on nothing.
  versions.py      comparison, per ecosystem (PEP 440, SemVer, bare tags) + the moving-tag rule
  advisories.py    merging aliased advisories, ranking, naming the one version that clears them
  config.py        .stocktake.toml / [tool.stocktake]; every value validated as it is read
  policy.py        decisions with a reason and an expiry; an overdue entry fails. Three kinds, and the
                   difference matters: ignore_advisories (one advisory), ignore_package (a package at a
                   version), hold_back (being out of date only -- never a vulnerability)
  scan.py          walking the tree, unread manifests, and which environment "installed" means
  evaluate.py      the judgement: Dep[] + registry answers -> Report. Pure given a Registries.
  check.py         one whole run, the fail/warn/skip rules, and assert_safe. THE RULES LIVE HERE ONCE.
  cli.py           argparse, exit codes, the init and vendor subcommands. The only module that prints.
  readers/         project files -> Dep[]. NEVER touch the network.
  registries/      names -> versions and advisories. NEVER touch the project.
  report/          pure functions of a Report: text, json, sarif, summary
  pytest_plugin.py the opt-in check as one pytest item. The only module that imports pytest.
  vendor.py        generates the single-file copy; refuses rather than emitting something wrong
vendored/          the generated copy, committed so a test can prove it is current
tests/             mirrors the above; test_guards.py holds the checks on StockTake itself
docs/adr/          why it is built the way it is. Read the index before changing anything fundamental.
```

## Conventions

- Ruff and mypy decide the style: 140 columns, strict typing over `src`. Fix warnings; never suppress without a comment saying why.
- **Comments say why, not what.** Most of the comments here exist because something was once wrong.
- Test names are sentences stating the expected behaviour. Long on purpose.
- **Never name anything `test*` in the package** — pytest collects it and the first test module that imports it fails.
- Module docstrings say what the module is for and which decision shaped it.

## How to build a change

1. Read `docs/HANDOFF.md`, then the ADR index if the change touches anything fundamental.
2. Write the test first for domain logic and for every bug fix.
3. Make the change. Keep the boundaries (see the map above) — they are what make this testable without a network.
4. `ruff check`, `ruff format`, `mypy`, `pytest`.
5. **`stocktake vendor vendored/` if anything under `src/stocktake/` changed.**
6. Run it against a real project, not only a fixture.
7. Update every doc the change affects, in the same commit.
8. Commit as a Conventional Commit whose body says why.

### Adding an ecosystem

One module in `readers/`, one in `registries/`, an import line in each `__init__.py`, and **a guard test** that counts what a fixture declares with an independent regular expression and insists the reader agrees. That is not optional: a clean-looking report that quietly missed half a project is the worst way this tool can fail.

**A reader raises `UnreadableManifest` when it cannot parse a file it claimed. It never returns nothing.** Returning an empty list for a truncated `package.json` is what gave a real project a clean report and exit 0, and nothing enforces this automatically — a reader that forgets re-creates that bug for its own file type ([ADR 0009](docs/adr/0009-an-unread-file-makes-the-run-incomplete.md)).

## Rules that must never be broken

- **It never edits a dependency**, with any flag, ever. The furthest it may go is printing the edit it would make.
- **It never executes anything it found.** No importing a scanned package, no lockfile scripts, no shelling out to a package manager.
- **Only package names and versions leave the machine.** No paths, no file contents, no telemetry.
- **A registry that cannot be reached is `unknown`, never clean.**
- **Only unsafe findings fail a build**; being behind warns ([ADR 0004](docs/adr/0004-only-unsafe-findings-fail-the-build.md)). "It would be more thorough to fail on X" has been considered and rejected.
- **A suppression is never a silence.** A policy entry may stop something failing the build; it may never stop it being reported. An accepted package lists every advisory it is carrying, in every format, and `--only` cannot narrow it away ([ADR 0011](docs/adr/0011-accepting-a-vulnerable-package.md)).
- **The runtime core depends on nothing.** A test enforces it.
- **The rules live in `check.py` only.** The CLI and the plugin both call them; neither works them out for itself.
- **Never weaken, skip or delete a test to get a passing run.** If a test is wrong, say why first.
- **Commit locally; never push.** The owner reviews and pushes. No history rewriting or force-pushing.
- **Ask before** changing the stack, adding any runtime dependency, publishing anything, or changing a decision an ADR records.

## Definition of done

1. It meets what was asked.
2. Tests cover the new behaviour; the whole suite passes.
3. Ruff, format and mypy clean.
4. You ran it on a real project.
5. `vendored/` regenerated if the core changed.
6. Docs updated in the same commit; an ADR for anything significant.
7. No leftover debug code or untracked TODOs; every TODO has a roadmap line.
8. Committed as a focused Conventional Commit.

## Reporting

At the end of a session, update `docs/HANDOFF.md` and report: what changed and what it means; what you verified, with the **actual** result; anything **unverified, said in those words**; what you decided and why; where you deviated from the plan and why; known issues; and what you recommend next.

**Verification is the point, not a formality.** Every bug found in this project so far was found by running the tool against a real project, never by reading the code. "Should work" is not verification. If you could not run something, say so and give the command.

## Session routine

Read `docs/HANDOFF.md` first. Update it last, with a session-log entry and anything the next session would otherwise rediscover.
