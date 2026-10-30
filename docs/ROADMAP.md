# StockTake: roadmap

Status values: `planned`, `in progress`, `done`. Each milestone is a vertical slice: the tool works end to end after every one.

## Now

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

## Next

### M2 — Drops into an existing test suite · size S · `planned`
**Goal.** Any project adds the check in one step without changing how its suite runs.

**Scope.** US-010, US-011, US-012
- `stocktake.pytest_plugin`, registered as a pytest11 entry point: the live check as one test, failing on `fail` findings and policy problems, warning on `outdated` through a `DependencyUpdateAvailable` warning in the summary, skipping on offline or `STOCKTAKE_OFFLINE`.
- `stocktake init` writes `tests/test_dependencies.py` from a template, for projects that would rather own the test file than enable a plugin.
- Documented behaviour for both paths, including what a CI run sees.

**Exit criteria.** A scratch project with an unrelated existing suite gains the check by adding one file, and `pytest` reports the outdated warning in its summary; with the network blocked the test skips and the suite still passes.

### M3 — npm, workflows and container tags · size M · `planned`
**Goal.** The web projects and the CI pipelines get the same check.

**Scope.** US-032, US-033
- `npm` reader: `package.json` plus `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock` for resolved versions; `registries/npm.py`; OSV ecosystem `npm`.
- `workflows` reader: `uses: owner/repo@ref` in `.github/workflows/*.yml`, comparing a pinned SHA or tag against the newest release. Add `.github/workflows/*.yml` to `MANIFEST_KINDS` in the *same* change, so this repository's own workflow becomes checked rather than merely unread — adding it before the reader exists would only force a self-exclusion.
- `containers`: `FROM image:tag` and `@sha256:` digests — is there a newer patch tag, has the tag moved.
- Per-ecosystem version comparison (SemVer for npm, PEP 440 for PyPI, bare integers for release tags), with the awkward cases as test cases.

**Exit criteria.** A real Node project reports npm findings that match `npm audit` on severity for the advisories both see, with the differences explained in the docs; a workflow pinned to an old action is reported with its newest release.

## Later

### M4 — SARIF, summary and the vendored copy · size M · `planned`
**Scope.** US-004, US-013, US-050
- SARIF 2.1.0 output with a result per finding, located at file and line, so GitHub's code-scanning view and editors can show them.
- `--format summary`: one line, for a status bar or a CI step name.
- `stocktake vendor <path>`: a single self-contained Python file, generated by concatenating the core modules in dependency order and stripping intra-package imports. Two guard tests keep it honest: regenerating must reproduce the committed copy byte for byte, and the core behavioural tests must pass against the vendored module as well as the package. Documented limitations: all readers bundled, no plugin discovery.

### M5 — Presentable in public · size S · `planned`
**Scope.** US-006 (readability), the public-facing half of G6
- README with real example output, the non-goals stated plainly, and a comparison table against Dependabot and Renovate.
- `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md`/`CLAUDE.md`, `docs/HANDOFF.md`.
- This repo runs its own check in CI and uploads the SARIF.
- Run it against three of the author's other projects, write down everything it gets wrong, and fix each with a regression test.
- Decide whether to publish to PyPI.

### M6 — More ecosystems · size L · `planned`
Go (`go.mod`, proxy.golang.org, OSV `Go`), Rust (`Cargo.toml`/`Cargo.lock`, crates.io, OSV `crates.io`), pre-commit hook pins, apt packages named in Dockerfiles. Each is one reader, one registry client, one guard test.

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

Carried over from the `ai-suite` original, to be addressed as noted:
- **GitHub release downloads get no advisory check.** OSV has no good key for a release binary. The writeup's idea of mapping to the Go or Cargo module it was built from is unproven. Tracked for M6; until then the docs say plainly that these get "newest tag" only.
- **Version comparison falls back to a tuple of integers** when `packaging` is absent, which mis-sorts pre-releases. Acceptable: the fallback has test cases for the cases that occur, and M3 makes comparison per-ecosystem.
- **The shared cache has no lock.** Two concurrent runs can have one overwrite the other's additions. Harmless (it only costs a request) but noted as PRD open question.

## Deferred decisions
- Whether `outdated` may fail behind a strictness flag — decided when a project asks for it, not before.
- Entry-point based reader discovery for out-of-tree readers — when someone outside this repo wants to write one.
- Private registry support — only as an explicit opt-in with its own credential handling, or not at all.
