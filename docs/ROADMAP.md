# StockTake: roadmap

Status values: `planned`, `in progress`, `done`. Each milestone is a vertical slice: the tool works end to end after every one.

## Done

### M0 — Walking skeleton: a Python project is checked, end to end · size M · `done` (2026-10-30)
**Goal.** `stocktake` installs, runs against a real Python project and prints a correct report, with the tooling and tests in place.

**Scope.** US-001, US-002, US-003, US-005, US-020, US-021, US-022, US-023, US-030, US-035
- Repo foundation: `pyproject.toml` (hatchling, PEP 621, console script), `.gitignore`, `.gitattributes`, `.editorconfig`, `.python-version`, ruff + mypy configuration, pytest configuration with the `network` marker, pre-commit hooks, a GitHub Actions workflow running lint, type check and tests.
- Core ported from `ai-suite/modules/depcheck`, split along the module boundaries in ARCHITECTURE.md: `models`, `versions`, `scan`, `evaluate`, `policy`, `report/text`, `report/json`.
- Readers: `dockerfile` (pip/uv/pipx pins, GitHub release downloads), `python_project` (`pyproject.toml` at the installed version).
- Registries: `pypi`, `github`, `osv` (PyPI ecosystem), with the six-hour cache and the offline/rate-limited distinction.
- Policy in TOML, read from `.stocktake.toml`, with reason and `until` and the overdue-entry failure.
- `stocktake` CLI: `--format text|json`, `--only all|outdated|vulnerable`, `--root`, `--config`, `--refresh`, `--all-advisories`, `--version`; exit codes 0/1/2.
- The 33 ported tests, adapted to the new module layout, plus guard tests for the missed-pin count.

**Exit criteria.** A fresh clone runs `uv sync && uv run pytest` green on Windows and Linux; `stocktake --root <a copy of ai-suite>` reproduces the findings the `ai-suite` version reports for the same input; `ruff check`, `ruff format --check` and `mypy` pass clean; README documents install and one command.

**What actually shipped**, where it differs from the plan above:
- 148 tests, not 33: splitting the module along its boundaries made several behaviours testable on their own that were previously only covered through the whole pipeline.
- `--policy` became `--config`, since the file holds the excludes as well as the policy.
- Exit code 2 also covers a config file that cannot be read, so a malformed policy can never silently fall back to defaults.
- Unread-manifest reporting (US-034) landed here rather than in M1: carrying it in the `Report` and rendering it was a few lines, and M1 now only has to make it configurable.
- Two extra modules the plan did not name: `advisories.py` (merging and ranking, pulled out of the registry client so `report/` can use it without importing `registries/`) and `readers/pep508.py` (what a Python requirement looks like, in one place, because both Dockerfile and manifest readers need it).
- `uv` is the documented install path but was not available on the development machine, so the suite was verified with `pip install -e` into a 3.11 virtual environment instead. CI covers 3.11 and 3.13 on Windows and Linux.
- A guard test asserts the core imports nothing outside the standard library, so ADR 0001's promise cannot be broken quietly.

**Verified.** 148 tests pass (including the live network check); `ruff check`, `ruff format --check` and `mypy --strict` clean; the scanner reproduces the original's output on `ai-suite`'s real manifests exactly — 40 dependencies, identical names, versions, sources and specifiers. CI itself is not verified until the branch is pushed.

### M1 — Config, excludes and the reader interface · size S · `done` (2026-10-30)
**Goal.** Nothing in the code knows about any particular project.

**Scope.** US-031, US-034, US-036, US-040, US-041
- `.stocktake.toml` loader: `ecosystems`, `exclude`, `cache.ttl_hours`, `[policy]`, with documented defaults and a clear error on a malformed file.
- Remove the hard-coded exclude list; defaults become the obvious ones (`.git`, `.venv`, `node_modules`, `__pycache__`, `dist`, `build`, `*.egg-info`).
- Formalise the `Reader` protocol and the reader registry; readers run only when their ecosystem is enabled.
- Unread-manifest reporting moves into config: a manifest kind with no reader is reported, and can be acknowledged in config rather than only by writing a reader.
- Readers added: `requirements*.txt`, `uv.lock`, `poetry.lock`, `Pipfile.lock`.
- One guard test per reader: an independent count of what the fixture declares against what the reader found.

**Exit criteria.** `stocktake` run against this repo, against a copy of `ai-suite` and against a Node project each read the right things and nothing else; a config naming only `python` makes no npm request (asserted by the fake network recording its calls).

**What actually shipped**, where it differs from the plan above:
- 221 tests, up from 148. Seven readers registered across two ecosystems.
- Two extra readers beyond the list: `pdm.lock` (the same shape as `uv.lock`, so free) and `Pipfile` itself. The Pipfile one is not padding: without it, a pipenv project would have been told its `Pipfile` was an unreadable manifest while its lock file was being read perfectly well — a false alarm, and the alternative was asking every pipenv project to write a self-exclusion.
- `accept_unread` and `environment` are config keys the plan did not name. The first is how a project acknowledges an unread manifest; the second came out of the bug below.
- **A correctness bug found during verification, and fixed: [ADR 0006](adr/0006-which-environment-an-installed-version-comes-from.md).** Milestone 0 inherited "ask whichever interpreter is running StockTake" for resolving declared ranges. As a standalone tool that is wrong — a demo project was reported as having `ruff 0.17.3` because that is what was in *StockTake's* virtual environment, and `uv tool install stocktake`, the recommended path, would have done the same to every project. Ranges are now resolved against the project's own environment, with `--environment PATH` to name one and an explicit note in the report when none can be found.
- `Report` gained a general `notes` channel for anything that affects how much of a report can be trusted, rendered above the findings.
- `Dep.role` gained the value `locked`, for a lock-file entry whose group the format does not record.
- The exit criterion's "against a Node project" could not be met and is not claimed: there is no npm reader until M3. The equivalent was asserted instead — a config naming only `python` makes no request to the GitHub releases API, proven by the fake network recording its calls.

**Verified.** 221 tests pass on 3.11 and 3.13; `ruff check`, `ruff format --check` and `mypy --strict` clean. The scanner still reproduces the original's output on `ai-suite`'s real manifests exactly (40 dependencies, no differences), so the M0 port fidelity is intact. Run against a project with `uv.lock` + `requirements-dev.txt`, all three new reader kinds produced correct findings against the real registries. Run against the author's brand-kit repository, pointed at its interpreter, it reported 58 advisories against the installed Pillow 11.2.1 and one against fonttools 4.58.0 — the first real finding in one of the author's own projects. CI still not verified (nothing pushed).

### M2 — Drops into an existing test suite · size S · `done` (2026-10-30)
**Goal.** Any project adds the check in one step without changing how its suite runs.

**Scope.** US-010, US-011, US-012
- `stocktake.pytest_plugin`, registered as a pytest11 entry point: the live check as one test, failing on `fail` findings and policy problems, warning on `outdated` through a `DependencyUpdateAvailable` warning in the summary, skipping on offline or `STOCKTAKE_OFFLINE`.
- `stocktake init` writes `tests/test_dependencies.py` from a template, for projects that would rather own the test file than enable a plugin.
- Documented behaviour for both paths, including what a CI run sees.

**Exit criteria.** A scratch project with an unrelated existing suite gains the check by adding one file, and `pytest` reports the outdated warning in its summary; with the network blocked the test skips and the suite still passes.

**What actually shipped**, where it differs from the plan above:
- **The plugin is opt-in, which the plan did not say and which turned out to be the decision of this milestone: [ADR 0007](adr/0007-the-pytest-plugin-is-opt-in.md).** A `pytest11` entry point alone would have made the check run in every suite in every environment where StockTake happened to be installed, including as a transitive dependency — adding network requests and build failures to projects whose maintainers had never heard of it. A project now switches it on with `stocktake = true`, or `--stocktake` for one run.
- `--no-stocktake`, a registered `stocktake` marker, and an explicit node id, so the check behaves like any other test under `-k`, `-m` and `-v`.
- `stocktake init` also writes a fully commented `.stocktake.toml`, so a project sees every key it might want without reading the README. It overwrites nothing without `--force`.
- `check.py` is new and was not in the plan: one whole run plus the fail/warn/skip rules, shared by the command line and the plugin so the two cannot drift. The CLI lost about 25 lines to it.
- **StockTake checks itself through its own plugin.** `stocktake = true` is in this repository's `pyproject.toml` and the hand-written live check it duplicated is gone, so the plugin's first consumer is this suite.
- `python -O` strips `assert`, which would have quietly disabled the failure. The plugin raises `AssertionError` explicitly instead; ruff's bandit rules found it.
- `init_project.test_file_template()` was renamed to `template_source()`: pytest collects anything named `test*`, so the original name was picked up as a test by the first test module that imported it.

**Verified.** 270 tests pass on 3.11 and 3.13; ruff and strict mypy clean. Both adoption paths were run end to end against a scratch project with a suite of its own and a live network: `stocktake init` then `pytest` gave `3 passed, 1 warning` with `click 8.1.7->8.5.0` named in the summary and exit 0; `STOCKTAKE_OFFLINE=1` gave `2 passed, 1 skipped` and exit 0; deleting the file and adding `stocktake = true` gave the same warning through the injected item. The plugin's collection, opt-in, opt-out and marker behaviour are covered by `pytester` tests that run a real pytest in a scratch project. CI still not verified (nothing pushed).

### M3 — npm, workflows and container tags · size M · `done` (2026-10-30), except containers (moved to M6)
**Goal.** The web projects and the CI pipelines get the same check.

**Scope.** US-032, US-033
- `npm` reader: `package.json` plus `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock` for resolved versions; `registries/npm.py`; OSV ecosystem `npm`.
- `workflows` reader: `uses: owner/repo@ref` in `.github/workflows/*.yml`, comparing a pinned SHA or tag against the newest release. Add `.github/workflows/*.yml` to `MANIFEST_KINDS` in the *same* change, so this repository's own workflow becomes checked rather than merely unread — adding it before the reader exists would only force a self-exclusion.
- `containers`: `FROM image:tag` and `@sha256:` digests — is there a newer patch tag, has the tag moved.
- Per-ecosystem version comparison (SemVer for npm, PEP 440 for PyPI, bare integers for release tags), with the awkward cases as test cases.

**Exit criteria.** A real Node project reports npm findings that match `npm audit` on severity for the advisories both see, with the differences explained in the docs; a workflow pinned to an old action is reported with its newest release.

**What actually shipped**, where it differs from the plan above:
- **`containers` is not done, and is moved to M6.** A Docker tag needs a registry client with an authentication dance (Docker Hub issues an anonymous bearer token before it will answer a manifest query), which is a different shape from the three read-only JSON APIs the tool uses now, and the first thing in StockTake that would need credential handling even for public data. npm and workflows together already deliver this milestone's goal — the web projects and the CI pipelines get the same check — so containers is better done properly later than squeezed in here.
- **`yarn.lock` and `pnpm-lock.yaml` are not read, and are moved to M6.** Both need a YAML parser, and the core has no dependencies ([ADR 0001](adr/0001-python-with-a-standard-library-only-core.md)). Regex-scanning them was considered and rejected: it is exactly the "misses things silently" failure the guard tests exist to prevent, and a guard written with a second regex would not be independent of the first. A yarn or pnpm project is still checked, because its `package.json` is read and resolved against `node_modules`, which holds the resolved truth those files describe — and both files are reported as unread, so nobody is told a project is clean when part of it was skipped.
- **A false positive found by running it on this repository, and the decision that came out of it: [ADR 0008](adr/0008-a-tag-its-publisher-moves-is-a-range.md).** The workflows reader's first run reported `actions/checkout 7->7.0.1` — an update that happens by itself, because GitHub advances the `v7` tag. `Dep.moving` now marks a tag its publisher advances, and such a tag is compared only to the precision it names. A real major gap is still reported, loudly.
- **One retry on a failed connection**, also found by verification: two of three requests to `api.github.com` failed TLS verification while every request to the other three services in the same run succeeded, and a later attempt to the same URLs worked. The tool was correct — it reported them as `unknown` with the reason, never as clean — but `unknown` for a dependency that is fine is noise. A service that *answered* is never retried.
- `Dep.note`, so a reader can say why there is no version to check. An action pinned to a commit SHA and an action tracking `@main` are both uncheckable for opposite reasons, and the report now says which.
- Per-ecosystem version comparison went in as planned: `semver_key` follows the SemVer specification's precedence rules, including the two a naive comparison gets backwards (a release outranks its own prerelease; a numeric prerelease identifier ranks below an alphanumeric one).

**Verified.** 342 tests pass on 3.11 and 3.13; ruff and strict mypy clean. Against a real 392-package Node project, StockTake and `npm audit` agreed exactly: the same two vulnerable packages (`electron`, `fast-uri`), the same severities, the same four advisories on `fast-uri`; StockTake also named the fix versions that `npm audit` only reports as available. The two differences that can occur in general are documented in the README. The workflows reader found `actions/checkout@v4 -> 7.0.1 (major)` and `actions/setup-python@v5 -> 7.1.0 (major)` in the author's brand-kit repository — three majors behind, and genuinely worth doing — while this repository's own `@v7` pins correctly report as current. A full uncached run of the 392-package project took 23 seconds. CI still not verified (nothing pushed).

### M4 — SARIF, summary and the vendored copy · size M · `done` (2026-10-30)
**Scope.** US-004, US-013, US-050
- SARIF 2.1.0 output with a result per finding, located at file and line, so GitHub's code-scanning view and editors can show them.
- `--format summary`: one line, for a status bar or a CI step name.
- `stocktake vendor <path>`: a single self-contained Python file, generated by concatenating the core modules in dependency order and stripping intra-package imports. Two guard tests keep it honest: regenerating must reproduce the committed copy byte for byte, and the core behavioural tests must pass against the vendored module as well as the package. Documented limitations: all readers bundled, no plugin discovery.

**What actually shipped**, where it differs from the plan above:
- **The SARIF is validated against the published schema, which cost one dev dependency.** `jsonschema` is in the `dev` extra for exactly that test. SARIF exists so that something else can read it, which makes "I believe this is valid" worth very little; a validator disagreeing is the only useful signal. Checked that the validator actually bites by feeding it a bad `level` and watching it refuse.
- **What goes into the SARIF is a judgement, not a translation.** Failures are `error`, informational findings are `note`, a `current` dependency is not a result at all, and a `held` one is a decision the project already recorded. Run-level facts — an environment that could not be found, registries that could not be reached — go in the invocation's notifications rather than being dressed up as findings. `Report.config_source` is new so that an overdue policy entry can be located at the config file that caused it instead of carrying an invented location.
- **The vendor equivalence guard is a focused test, not the whole suite run twice**, which is what [ADR 0005](adr/0005-installed-package-plus-a-generated-single-file-copy.md) had promised. The amendment on that record explains why and what replaced it: both are run against one fixture exercising five readers and three ecosystems, and the text, JSON *and* SARIF reports must be identical, with a second test proving the fixture really produces findings so the comparison cannot pass vacuously.
- **Most of the generator's value turned out to be in refusing.** It stops rather than emitting on a name defined twice (in one flat file the second wins silently), on a module importing something left out, on an import cycle, and on nothing to copy. The second of those caught a real bug immediately: `cli.py` imports `init_project.py`, so the command line had to be excluded from the copy too. Dependency order is computed from the imports rather than listed, so the generator cannot fall behind the package.
- Intra-package imports that *renamed* something (`from stocktake.readers import groups as reader_groups`) are restored at the end of the generated file. Without that the copy would have raised `NameError` — not at import, but at the moment somebody's config named an ecosystem that does not exist.
- The CI workflow now uploads the SARIF to code scanning on a push, which was an M5 item.

**Verified.** 407 tests pass on 3.11 and 3.13; ruff and strict mypy clean. The SARIF produced from a real 392-package project validates against the published SARIF 2.1.0 schema: 195 results, 3 errors and 192 notes, located at `package-lock.json` with `%SRCROOT%`. **The vendored file was copied to a directory of its own and run by a different interpreter with no `stocktake` installed, against that same real project, and produced the same three vulnerable findings** — which is US-013 as written. The byte-for-byte guard earned its keep within the session: a `ruff format` pass touched one core module, the committed copy went stale, and the test caught it.

**Settled after the push on 2026-10-30:** the code-scanning job ran and **GitHub accepted the SARIF** — an analysis is recorded against the repository under tool `StockTake`, category `stocktake`. That is better evidence than the schema validator: the consumer the format exists for ingested it. The same run also showed the job was installing `-e .` without the dev extra, so this project's own dev dependencies had nothing to resolve against and arrived as four `unpinned` notes about its own tooling — correct, and useless. Fixed.

### M5 — Presentable in public · size S · `done` (2026-10-30), bar two things the owner decides
**Scope.** US-006 (readability), the public-facing half of G6
- README with real example output, the non-goals stated plainly, and a comparison table against Dependabot and Renovate.
- `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md`/`CLAUDE.md`, `docs/HANDOFF.md`.
- This repo runs its own check in CI and uploads the SARIF.
- Run it against three of the author's other projects, write down everything it gets wrong, and fix each with a regression test.
- Decide whether to publish to PyPI.

**What actually shipped**
- `CHANGELOG.md` (Keep a Changelog; everything under *Unreleased*, because nothing has been released), `CONTRIBUTING.md`, `AGENTS.md` with a `CLAUDE.md` importing it. README gained a "Does it work?" section built out of what the real runs found, and links to the new documents.
- **Run against four more real projects** — `financial-chatbot` (a Dockerfile, a `requirements.txt`, three `package.json`/lock pairs and six workflow files), `pixel-galaxy-studio`, `MyEdMaster-FinancialEducation-Chatbot` and `Brand Logos` — on top of `DayandNight_BCS` from M3. About two thousand dependencies in total. Vulnerable dependencies in every one of them.
- **One class of thing it got wrong, found that way and fixed with six regression tests:** advice aimed at the wrong ecosystem. `pixel-galaxy-studio` has no Python in it at all and was being told to point StockTake at a Python environment, which cannot help it and makes the rest of the report look careless. Run-level notes are now tied to the ecosystem they are about, and a Node project whose `node_modules` is missing is told to run `npm install` instead. The per-finding note changed too: "not installed in this environment" reads as a Python environment and means nothing to somebody reading a Node project's report.
- **One thing that looked wrong and was not**, worth recording so it is not "fixed" later: `financial-chatbot/backend/Dockerfile` produced no findings. Its only install is `RUN pip install -r requirements.txt`, which names no packages — and that `requirements.txt` is read on its own account, yielding 14. The reader is right.

**Verified.** 413 tests on 3.11 and 3.13; ruff and strict mypy clean. The real-project runs are in the session scratchpad, not the repository.

**Settled after the push on 2026-10-30:** CI passes on all four matrix jobs — Windows and Ubuntu, 3.11 and 3.13 — which is the first time Linux has been exercised at all. `pip install git+…` was verified in a clean 3.13 environment to give the complete build, so the install route the README documents for CI is correct. `pip install stocktake` still fails, by choice.

**Left for the owner, not decided here:**
- **The logo.** The brand kit has no `stocktake` brand, and its own note says to ask when a brand has no generated assets. The company's shared mark exists at `Brand Logos/dist/black-canyon-software/` in several lockups; whether StockTake should borrow that or get an entry of its own in the kit is a branding decision, and that work belongs in the brand repository rather than this one.
- **PyPI.** The packaging metadata is complete and the name was still unclaimed on 2026-10-30. Publishing is outward-facing and effectively permanent, so it waits for an explicit decision.

## Now

### M6 — More ecosystems · size L · `planned`
Each is one reader, one registry client, one guard test. The first two are carried over from M3 and are the ones a real project is most likely to want next:

- **Containers:** `FROM image:tag` and `@sha256:` digests. The work that is not in the reader: Docker Hub issues an anonymous bearer token before it will answer a manifest query, so this is the first registry client needing an authentication step even for public data, and the first that cannot simply be a GET of a JSON document. A moving tag like `python:3.12` is handled by [ADR 0008](adr/0008-a-tag-its-publisher-moves-is-a-range.md), which already exists for this.
- **`yarn.lock` and `pnpm-lock.yaml`:** both need YAML. The options are a vendored minimal parser for the subset these files use, or accepting a dependency and amending [ADR 0001](adr/0001-python-with-a-standard-library-only-core.md). Regex-scanning them is **not** an option: it is the "misses things silently" failure the guard tests exist to catch, and a guard written with a second regex would not be independent of the first.
- Go (`go.mod`, proxy.golang.org, OSV `Go`), Rust (`Cargo.toml`/`Cargo.lock`, crates.io, OSV `crates.io`), pre-commit hook pins, apt packages named in Dockerfiles, conda `environment.yml`.

### M7 — `propose` mode · size M · `planned`
Print the exact edit that would fix each finding, with a changelog or compare link. It never applies it. Needs a careful answer to "what is the right target version" per ecosystem; the advisory fix target already solves half of it.

## Tech debt and known gaps
Every `TODO` in the code gets a line here. There are none.

- **This repository's own GitHub Actions pins are not checked.** `.github/workflows/ci.yml` pins `actions/checkout@v7` and `actions/setup-python@v7` by tag, and nothing watches them. Tracked in M3, which adds the reader and the manifest kind together.
- **`role` is a bare string**, now with five values (`runtime`, `dev`, `image`, `locked`, and `ci` from M3). It wants to be an enum once M3 settles what the values actually are.
- **A `requirements.txt`'s role is guessed from its filename.** `requirements-dev.txt` is treated as dev, `requirements.txt` as runtime. The format offers no other hint. Informational only: role changes nothing about whether a finding fails.
- **Lock-file entries carry no line number**, only the file, because the TOML and JSON parsers do not report one. Findable by searching the text for the name, which is fragile; not worth it yet.
- **`dist-info` directory names are trusted** for installed versions rather than the metadata inside them (ADR 0006). The documented layout, and what makes the lookup free.
- **A project whose environment is in none of the usual places needs `--environment` passing once.** The brand-kit repository is this case. A config entry makes it permanent, but it has to be discovered first; the report's note is what makes that discoverable.

From M4:
- **The committed copy in `vendored/` has to be regenerated whenever the core changes.** A test fails when it is stale, so it cannot be forgotten, but it is a step: `stocktake vendor vendored/`. A pre-commit hook or a CI step that regenerates and diffs would remove the manual part.
- **The core must stay concatenatable**: no two core modules may define the same top-level name, and none may import something the copy leaves out. Free today (no collisions across 30 files and 178 names), but it is a real constraint, and the generator is where it is enforced.
- **`vendored/` is excluded from ruff and mypy.** Formatting it would break the byte-for-byte guard, and its contents are the concatenation of files already checked here. The cost is that a syntax error in the generated file is caught by the tests that import it rather than by lint.
- **The SARIF schema is fetched over the network** by the test that validates against it, so that test skips offline. Vendoring the schema would make it offline-proof at the cost of ~250KB of somebody else's JSON in the repository.
- **`uriBaseId: "%SRCROOT%"` assumes the project root is the repository root.** True for every project seen so far, wrong for a project checked from a subdirectory of a monorepo.

From M3:
- **Nothing reports a dependency as pinned too loosely.** `uses: actions/checkout@v7` is a moving tag, and a compromised tag is a real supply-chain risk that SHA pinning exists to address; the same goes for an npm `^1.2.3`. [ADR 0008](adr/0008-a-tag-its-publisher-moves-is-a-range.md) deliberately says nothing about it rather than conflating it with being out of date. The right shape is a separate opt-in finding, not a change to how `outdated` works.
- **A commit-pinned action with no version comment cannot be compared.** It is reported with the reason and how to fix it. Resolving the SHA to a release would mean listing a repository's tags and matching SHAs — one or two extra requests per action against a 60-an-hour anonymous limit.
- **An npm package declared in both `package.json` and the lock file is two findings.** Correct — fixing it means editing both — but it makes StockTake's headline count higher than `npm audit`'s. Documented in the README rather than changed.
- **`node_modules` is read for every declared name, one small file at a time.** Fine for the hundreds a project declares; it would want batching if something ever asks about the whole tree.

From M2:
- **A project that runs `stocktake init` and also sets `stocktake = true` checks itself twice.** Harmless — the second run is served entirely from the six-hour cache — and there is a test recording it, but it would be friendlier for the plugin to notice the written file and stand down.
- **The injected item has no file of its own**, so its reported location is the project root and `--junitxml` records it with no classname. There is nowhere more honest to point, but a CI dashboard will show it oddly.
- **`stocktake init` does not offer to switch the plugin on instead.** Someone running `init` may not know the one-line option exists; the command could say so.

Carried over from the `ai-suite` original, to be addressed as noted:
- **GitHub release downloads get no advisory check.** OSV has no good key for a release binary. The writeup's idea of mapping to the Go or Cargo module it was built from is unproven. Tracked for M6; until then the docs say plainly that these get "newest tag" only.
- **Version comparison falls back to a tuple of integers** when `packaging` is absent, which mis-sorts pre-releases. Acceptable: the fallback has test cases for the cases that occur, and M3 makes comparison per-ecosystem.
- **The shared cache has no lock.** Two concurrent runs can have one overwrite the other's additions. Harmless (it only costs a request) but noted as PRD open question.

## Deferred decisions
- Whether `outdated` may fail behind a strictness flag — decided when a project asks for it, not before.
- Entry-point based reader discovery for out-of-tree readers — when someone outside this repo wants to write one.
- Private registry support — only as an explicit opt-in with its own credential handling, or not at all.
