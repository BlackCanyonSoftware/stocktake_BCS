# StockTake: handoff

## Current state
**Milestones 0 to 5 are done and verified**, except container tags, which moved to M6 (see the roadmap for why). 413 passing tests on Python 3.11 and 3.13, clean lint, clean strict type checking. The next session starts Milestone 6, or the two decisions M5 left to the owner.

**It has been run against five real projects** — about two thousand dependencies, Python, Node and mixed — and found vulnerable dependencies in every one. Three of its own bugs were found that way and only that way.

It reads **four ecosystems**: `python` (seven manifest kinds), `npm` (`package.json`, `package-lock.json`, `node_modules`), `workflows` (GitHub Actions pins) and `binaries` (GitHub release downloads). It reports as text, JSON, SARIF or one line. It drops into another project's pytest suite in one line, writes its own test file with `stocktake init`, and writes itself as one dependency-free file with `stocktake vendor`.

**It checks itself through its own plugin.** `stocktake = true` is in this repository's `pyproject.toml`, so every `pytest` run here exercises the thing other projects will use. If the plugin breaks, this suite notices first.

Commits are local only. Nothing has been pushed; CI has therefore never run and is **not verified**.

```bash
py -3.11 -m venv .venv
./.venv/Scripts/python -m pip install -e ".[dev]"   # .venv/bin/python on macOS and Linux
./.venv/Scripts/python -m pytest                    # 413 tests, ~6s (includes the live check, via the plugin)
./.venv/Scripts/stocktake vendor vendored/          # after ANY change to the core, or a test fails
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
- A declared range is resolved against the *project's* environment or not at all, never against StockTake's own — [ADR 0006](adr/0006-which-environment-an-installed-version-comes-from.md)
- The pytest plugin is **opt-in**; installing the package must change nothing about anybody's test run — [ADR 0007](adr/0007-the-pytest-plugin-is-opt-in.md)
- A tag its publisher advances (`@v7`, `python:3.12`) is a range, compared only to the precision it names — [ADR 0008](adr/0008-a-tag-its-publisher-moves-is-a-range.md)
- The vendored copy's equivalence guard is a focused comparison, not the whole suite run twice — the amendment on [ADR 0005](adr/0005-installed-package-plus-a-generated-single-file-copy.md)
- Scope confirmed by the owner on 2026-10-29: Python + npm + GitHub Actions + container tags for v1; MIT licence; package plus vendor command; leave `ai-suite` alone.

## Work in progress
None. M0 to M5 are complete; M6 has not been started.

## Next steps
1. **Two decisions the owner has to make**, both recorded in [ROADMAP.md](ROADMAP.md) under M5 and in the PRD's open questions: whether to publish to PyPI (metadata is ready, the name was free on 2026-10-30), and whether StockTake gets its own brand-kit entry or borrows the company mark. Neither is a coding task; the second one's work lives in the brand repository.
2. **Switch the check on in the projects it was run against.** They have been *checked* but have not *adopted* it — nothing was changed in any of them. One line (`stocktake = true`) or one command (`stocktake init`) each.
3. **Push, so CI is verified for the first time.** It has never run. The code-scanning upload step in particular cannot be verified any other way.
4. **Milestone 6** when there is appetite: container tags and the YAML lock files, both carried over from M3 with reasons.

**Known findings in the author's own repositories. Nothing was changed in any of them, and none of this has been acted on.**
- `Brand Logos`: installed Pillow 11.2.1 has 58 advisories (5 critical), fonttools 4.58.0 has 1. Both declared as ranges, so the pins are not wrong — the installed versions are old. Its CI pins `actions/checkout@v4` and `actions/setup-python@v5`, three majors behind. Needs `--environment` (it installs into the global Python).
- `DayandNight_BCS`: `electron` 44.9.0 (1 high, fixed in 44.9.1) and `fast-uri` 3.1.8 (4 advisories, fixed in 3.1.9), agreeing exactly with `npm audit`. CI pins `actions/checkout@v5`.
- `pixel-galaxy-studio`: **the worst of the five.** `tar 6.2.1` with 12 advisories including one critical, `electron 33.4.11` with 46, plus `app-builder-lib`, `builder-util-runtime`, `extract-zip` (2 high, and no fixed version is named) and `ip-address`. CI pins four actions at `@v4`, three majors behind. No `node_modules`, so its `package.json` ranges are unresolved.
- `MyEdMaster-FinancialEducation-Chatbot`: **18 vulnerable**, the highest count of the five. Python `requirements.txt` plus a Node frontend.
- `financial-chatbot`: 4 vulnerable (`zod` at three different versions across three lockfiles, `fast-uri`). Notable as the richest test case available — a Dockerfile, a `requirements.txt`, three `package.json`/lock pairs and six workflow files, 768 dependencies. Its actions are pinned to commit SHAs *with* version comments, which is the good practice the workflows reader is built to read.

## How M0 and M1 were verified, and what that did not cover
- 221 tests pass on Python 3.11 and 3.13, including the one marked `network` that asks the real registries about this project's own dependencies.
- `ruff check`, `ruff format --check` and `mypy` (strict, on `src`) are clean.
- **The port is exact, and still is after M1.** The scanner was run against `ai-suite`'s real `docker/dev/Dockerfile`, `docker/llama-swap/Dockerfile` and `pyproject.toml`, and compared against the original scanner's output on the same files: 40 dependencies, identical names, versions, source locations and specifiers, no differences at all. The comparison script is in the session scratchpad, not the repository — rebuild it if the port fidelity ever needs re-checking.
- A real run against a project pinning `pillow==9.0.0` and `requests==2.19.1` found 52 and 5 advisories respectively and named `13.0.0` and `2.33.0` as the versions that clear them — matching what the original writeup reported for Pillow.
- A real run against a project with `uv.lock` plus `requirements-dev.txt` exercised all three new reader kinds against the real registries, including the project's own package being correctly skipped in the lock file.
- **Both adoption paths, end to end, on a scratch project with a suite of its own and a live network.** `stocktake init` then `pytest`: `3 passed, 1 warning`, with `click 8.1.7->8.5.0` named in the warnings summary, exit 0. `STOCKTAKE_OFFLINE=1`: `2 passed, 1 skipped`, exit 0. Deleting the written file and adding `stocktake = true` instead: the same warning, through the injected item. That is the M2 exit criterion, met as written.
- **A real finding in one of the author's own projects.** Pointed at the brand-kit repository with `--environment`, it reported 58 advisories (5 critical) against the installed Pillow 11.2.1 and one against fonttools 4.58.0. Both are declared as ranges (`Pillow>=10.0`, `fonttools>=4.40`), so nothing was pinned wrongly — the installed versions are simply old. **This has not been acted on and the owner has not been asked about it.**
- **A real 392-package Node project (`DayandNight_BCS`), against `npm audit`.** Exact agreement: the same two vulnerable packages, the same severities, the same four advisories on `fast-uri`. StockTake additionally named the fix versions. An uncached run took 23 seconds.
- **The workflows reader on two real repositories.** It found genuine major gaps in the brand kit (`actions/checkout@v4` → 7.0.1) while correctly staying silent about this repository's own `@v7` pins.
- **The SARIF from a real project validates against the published SARIF 2.1.0 schema.** 195 results from the 392-package project, 3 errors and 192 notes, located at `package-lock.json`. The validator was checked against a deliberately broken `level` to confirm it actually refuses things.
- **The vendored single file, run standalone.** Copied to a directory of its own and executed by a different interpreter with no `stocktake` installed, against the same real project: the same three vulnerable findings. That is US-013 as written.
- **Not covered:** CI (never pushed, and the new code-scanning upload step especially), macOS, Python 3.12, container base images, yarn and pnpm lock files, and any ecosystem beyond the four.

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
- **"The installed version" is not a simple question, and getting it wrong is silent.** See [ADR 0006](adr/0006-which-environment-an-installed-version-comes-from.md). The inherited behaviour asked whichever interpreter was running StockTake, which is the *wrong* environment for every installation path except "dev dependency of the project being checked". If anything in this area is ever simplified, re-read that ADR first.
- **Pins and ranges are resolved in opposite directions, on purpose.** A lock file or a `==` pin wins over what is installed (it names what *will* be installed); a `pyproject.toml` or `Pipfile` range loses to what is installed (the range says nothing about what is running). Two rules, each with its own rationale, both in the reader docstrings.
- **`DEV_WORDS` in the requirements reader is matched as whole words, not substrings.** `requirements-social.txt` contains "ci". There is a test for exactly that.
- **An environment that exists and is empty is not the same as no environment at all.** `_read_site_packages` returns `{}` for the first and `None` for the second; conflating them made an empty virtual environment fall through to the next candidate.
- **Never name anything `test*` in the package.** pytest collects it, and the first test module that imports it fails for returning a value. `init_project.test_file_template` had to become `template_source`.
- **`python -O` strips `assert`.** The plugin raises `AssertionError` explicitly for exactly that reason; an `assert` there would have left suites passing for the wrong reason under `-O`. Ruff's bandit rules (S101) are what caught it, which is why `S` is in the selected rule set.
- **`pytest_plugins` must be declared in the *root* conftest.** That is the only reason `conftest.py` exists at the top of this repository.
- **The plugin's hook is `tryfirst` on purpose.** It appends the item before pytest's own `-k`/`-m` filtering runs, so selection still applies to it. Make it `trylast` and `-m "not stocktake"` silently stops working.
- **Test the plugin through `pytester`, not through its internals.** `tests/test_pytest_plugin.py` runs a real pytest in a scratch project with `STOCKTAKE_OFFLINE=1`, so it is fast, deterministic and asserts on what a project's suite actually sees.
- **Not every "version" is a version.** `@v7` is a tag GitHub advances, so it is a range; see [ADR 0008](adr/0008-a-tag-its-publisher-moves-is-a-range.md) before touching `Dep.moving` or `is_newer`. A reader that forgets to set `moving` produces exactly the false positive that record is about.
- **`normalize` is not what a registry is asked for.** `normalize` is StockTake's internal comparison key, the same rule for every ecosystem, used for policy matching and advisory keys. `registry_name` is what goes on the wire: PyPI normalises, npm is case-sensitive and takes the name as written. Mixing them up means 404s on scoped npm packages.
- **`api.github.com` fails TLS verification intermittently on this machine.** Two of three requests failed in one run and the same URLs worked later. That is why `default_fetch` retries once. If it ever gets worse, the cause is worth finding; it looks like TLS interception rather than anything in the tool.
- **`npm audit` is the right thing to check the npm reader against**, and npm 11.20.0 is installed on this machine. `npm audit --json` on a project, then compare: the comparison script is in the session scratchpad, not the repository.
- **Regenerate `vendored/` after any change to the core**, with `stocktake vendor vendored/`. A test fails when it is stale, which is how this is remembered; a `ruff format` pass is enough to stale it.
- **Loading the vendored file by path needs it in `sys.modules` first.** An ordinary `import stocktake_vendored` does that; `module_from_spec` + `exec_module` without it breaks `@dataclass` under postponed annotations, because the dataclass machinery looks the module up there to resolve `ClassVar`. `tests/test_vendor.py` has the working loader.
- **The core must stay concatenatable.** No two core modules may define the same top-level name, and none may import something `vendor.py` excludes (the command line, `init_project`, the pytest plugin). The generator refuses rather than emitting, so this shows up as a clear failure rather than a subtly wrong copy.
- **A guard written by matching lines will bite you.** The stdlib-only guard used to scan for lines starting with `import`, and `vendor.py`'s docstring contains an example `import stocktake_vendored`. It now parses with `ast`, which also catches imports inside functions.
- **Advice has to be tied to the ecosystem it is about.** `notes_about()` in `check.py` emits the Python-environment note only when a *PyPI* range went unresolved, and the npm note only when an npm one did. Before that, a pure Node project was told to pass `--environment`, which cannot help it. Six regression tests cover the combinations.
- **A Dockerfile whose only install is `RUN pip install -r requirements.txt` correctly yields nothing.** The `-r` consumes the filename, no package is named on the line, and the `requirements.txt` is read on its own account. This looks like a miss and is not; do not "fix" it.
- **`uv` is still not installed on this machine**, and nothing has been installed without asking. The repo is developed with `py -3.11 -m venv` plus `pip install -e`. The 3.13 environment used for the second test run lives in the session scratchpad, not the repo.

## Projects to try it on (M5)
The owner has about ten repositories available for this, and the list is the most valuable thing M5 can have. Known so far:
- `ai-suite` on KPrime — the reference. Dockerfile pip pins, GitHub release downloads, `pyproject.toml` dev dependencies. Already compared against, scanner-only.
- `Documents/Brand Logos` (the brand kit) — a real Python project with pytest, pre-commit, Dependabot and `.github/workflows`, so it exercises the workflow reader when M3 lands and gives a direct comparison against what Dependabot reports. **Already run against** (see above): it has no virtual environment of its own and installs into the user's global Python, so it needs `--environment C:/Users/Kpier/AppData/Local/Programs/Python/Python313` (or an `environment` entry in its own `.stocktake.toml`). Its `.pre-commit-config.yaml` is reported as unread, correctly.
- **Node projects, all with `package-lock.json`:** `DayandNight_BCS` (another Black Canyon project; lockfileVersion 3, 395 packages, already verified against `npm audit`), `pixel-galaxy-studio` (480 packages), `financial-chatbot` (three manifests: root, `frontend/`, `video-pipeline/`), `MyEdMaster-FinancialEducation-Chatbot` (`frontend/`).
- **Ask the owner for the remaining names and note them here.** About ten repositories were mentioned; six have been found on the machine so far.

## Open questions for the owner
In [PRD.md](PRD.md) under "Open questions". None block M1. The one worth deciding soonest: whether to publish `stocktake` to PyPI now (the name is free as of 2026-10-29) or wait until there are two real consumers.

## Session log
### Session 7 — 2026-10-30
Built Milestone 5: `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md` with `CLAUDE.md`, and a README section built out of what the real runs found. Ran the tool against four more real projects — about two thousand dependencies across Python, Node and mixed — and fixed the one class of thing it got wrong: run-level advice aimed at the wrong ecosystem, with six regression tests. Recorded one thing that looked wrong and was not. 407 → 413 tests. Left the logo and the PyPI decision to the owner, with the options written down. Committed locally; not pushed.

### Session 6 — 2026-10-30
Built Milestone 4: SARIF 2.1.0 output (validated against the published schema by the test suite, with `jsonschema` added to the dev extra for that one job), `--format summary`, and `stocktake vendor` — a generator that emits the core as one flat file in computed dependency order and refuses rather than emitting on a duplicated name, a missing dependency, a cycle or an empty core. The copy is committed in `vendored/` and three guards hold it in place. Amended [ADR 0005](adr/0005-installed-package-plus-a-generated-single-file-copy.md) where the equivalence guard differs from what it promised. 342 → 407 tests. The vendored file was verified standalone, by another interpreter with nothing installed, against a real 392-package project. Committed locally; not pushed.

### Session 5 — 2026-10-30
Built Milestone 3 except containers: the `npm` ecosystem (`package.json`, `package-lock.json` in both layouts, ranges resolved against `node_modules` including hoisting, the npm registry, OSV's `npm` ecosystem) and the `workflows` ecosystem (GitHub Actions `uses:` pins, with commit SHAs read from the conventional version comment). SemVer comparison added, so version rules are now per ecosystem. Two problems found by running it on real projects and fixed: the moving-tag false positive ([ADR 0008](adr/0008-a-tag-its-publisher-moves-is-a-range.md)) and transient connection failures becoming false `unknown`s. Containers and the YAML lock files moved to M6 with reasons. 270 → 342 tests. Verified against `npm audit` on a real 392-package project, with exact agreement. Committed locally; not pushed.

### Session 4 — 2026-10-30
Built Milestone 2: the opt-in pytest plugin ([ADR 0007](adr/0007-the-pytest-plugin-is-opt-in.md)), `stocktake init`, and `check.py` holding one whole run plus the fail/warn/skip rules that the command line and the plugin now share. StockTake switched to checking itself through its own plugin, and the hand-written live test it duplicated was deleted. 221 → 270 tests. Both adoption paths verified end to end against a scratch project with a live network, and both verified to skip and stay green with the network declared unreachable. Committed locally; not pushed.

### Session 3 — 2026-10-30
Built Milestone 1: `.stocktake.toml` gained `ecosystems`, `accept_unread`, `environment` and `cache.ttl_hours`, all validated on read; readers added for `requirements*.txt`, `constraints*.txt`, `uv.lock`, `pdm.lock`, `poetry.lock`, `Pipfile.lock` and `Pipfile`, each with a guard test counting independently of the reader; unread manifests split into reported and accepted, so an acceptance stops the nagging without becoming invisible. Found and fixed a correctness bug in the inherited range-resolution ([ADR 0006](adr/0006-which-environment-an-installed-version-comes-from.md)) and added `--environment`. 148 → 221 tests. Verified as described above, including the first real finding in one of the owner's own projects. Committed locally; not pushed.

### Session 2 — 2026-10-30
Built Milestone 0: repo foundation (`pyproject.toml`, ruff, mypy, pytest, CI workflow, ignore and editor files), the core ported from `ai-suite/modules/depcheck/__init__.py` and split into 20 modules along the boundaries in ARCHITECTURE.md, 148 tests, README, and three documentation corrections where the code ended up differing from the plan (`--config` not `--policy`, exit code 2's meaning, the real `Reader` shape). Verified as described above. Committed locally; not pushed.

### Session 1 — 2026-10-29
Read the writeup and the house project standards; pulled the five reference files from `ai-suite` on KPrime into the scratchpad; confirmed four scope decisions with the owner; wrote `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/DESIGN.md` and ADRs 0001–0005; committed locally. Stopped at the approval pause before any code, per the workflow. No code was written, so nothing was tested.
