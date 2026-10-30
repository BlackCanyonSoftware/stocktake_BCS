# StockTake: roadmap

Status values: `planned`, `in progress`, `done`. Each milestone is a vertical slice: the tool works end to end after every one.

## Now

### M0 — Walking skeleton: a Python project is checked, end to end · size M · `planned`
**Goal.** `stocktake` installs, runs against a real Python project and prints a correct report, with the tooling and tests in place.

**Scope.** US-001, US-002, US-003, US-005, US-020, US-021, US-022, US-023, US-030, US-035
- Repo foundation: `pyproject.toml` (hatchling, PEP 621, console script), `.gitignore`, `.gitattributes`, `.editorconfig`, `.python-version`, ruff + mypy configuration, pytest configuration with the `network` marker, pre-commit hooks, a GitHub Actions workflow running lint, type check and tests.
- Core ported from `ai-suite/modules/depcheck`, split along the module boundaries in ARCHITECTURE.md: `models`, `versions`, `scan`, `evaluate`, `policy`, `report/text`, `report/json`.
- Readers: `dockerfile` (pip/uv/pipx pins, GitHub release downloads), `python_project` (`pyproject.toml` at the installed version).
- Registries: `pypi`, `github`, `osv` (PyPI ecosystem), with the six-hour cache and the offline/rate-limited distinction.
- Policy in TOML, read from `.stocktake.toml`, with reason and `until` and the overdue-entry failure.
- `stocktake` CLI: `--format text|json`, `--only all|outdated|vulnerable`, `--root`, `--policy`, `--refresh`, `--all-advisories`; exit codes 0/1/2.
- The 33 ported tests, adapted to the new module layout, plus guard tests for the missed-pin count.

**Exit criteria.** A fresh clone runs `uv sync && uv run pytest` green on Windows and Linux; `stocktake --root <a copy of ai-suite>` reproduces the findings the `ai-suite` version reports for the same input; `ruff check`, `ruff format --check` and `mypy` pass clean; README documents install and one command.

### M1 — Config, excludes and the reader interface · size S · `planned`
**Goal.** Nothing in the code knows about any particular project.

**Scope.** US-031, US-034, US-040, US-041
- `.stocktake.toml` loader: `ecosystems`, `exclude`, `cache.ttl_hours`, `[policy]`, with documented defaults and a clear error on a malformed file.
- Remove the hard-coded exclude list; defaults become the obvious ones (`.git`, `.venv`, `node_modules`, `__pycache__`, `dist`, `build`, `*.egg-info`).
- Formalise the `Reader` protocol and the reader registry; readers run only when their ecosystem is enabled.
- Unread-manifest reporting moves into config: a manifest kind with no reader is reported, and can be acknowledged in config rather than only by writing a reader.
- Readers added: `requirements*.txt`, `uv.lock`, `poetry.lock`, `Pipfile.lock`.
- One guard test per reader: an independent count of what the fixture declares against what the reader found.

**Exit criteria.** `stocktake` run against this repo, against a copy of `ai-suite` and against a Node project each read the right things and nothing else; a config naming only `python` makes no npm request (asserted by the fake network recording its calls).

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
- `workflows` reader: `uses: owner/repo@ref` in `.github/workflows/*.yml`, comparing a pinned SHA or tag against the newest release.
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
Nothing yet — the project has no code. Entries get added here as they appear, and every `TODO` in the code gets a line here.

Carried over from the `ai-suite` original, to be addressed as noted:
- **GitHub release downloads get no advisory check.** OSV has no good key for a release binary. The writeup's idea of mapping to the Go or Cargo module it was built from is unproven. Tracked for M6; until then the docs say plainly that these get "newest tag" only.
- **Version comparison falls back to a tuple of integers** when `packaging` is absent, which mis-sorts pre-releases. Acceptable: the fallback has test cases for the cases that occur, and M3 makes comparison per-ecosystem.
- **The shared cache has no lock.** Two concurrent runs can have one overwrite the other's additions. Harmless (it only costs a request) but noted as PRD open question.

## Deferred decisions
- Whether `outdated` may fail behind a strictness flag — decided when a project asks for it, not before.
- Entry-point based reader discovery for out-of-tree readers — when someone outside this repo wants to write one.
- Private registry support — only as an explicit opt-in with its own credential handling, or not at all.
