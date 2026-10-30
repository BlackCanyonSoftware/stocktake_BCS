# StockTake: product requirements

## Problem and vision
A project's dependency pins rot quietly. The pin that was fine when it was written picks up a security advisory months later, and nothing in the project says so. The hosted answers to this (Dependabot, Renovate) want a GitHub repository, open pull requests on their own schedule, and cannot see a pin that lives inside a Dockerfile `RUN pip install ...` line or a version that is only true of the machine you develop on.

StockTake is a stock-take of what a project depends on, run locally, as part of that project's own test suite. It reads what the project pins, asks the public registries whether a newer release exists and whether the pinned one has a known advisory, and fails the tests only when something is actually unsafe. It never edits a file, never needs an account, and sends nothing but package names and versions.

The measure of success is boring: it stays switched on. A checker that fails the build for being six months behind gets disabled within a week, and then it protects nothing.

## Target users
- **Primary: the maintainer of several small-to-medium projects** (the author) running a mixed estate of Python services, Dockerised dev images and web apps, who wants one check that drops into each project's existing test suite without a per-project rewrite.
- **Secondary: a developer on any small team** who wants a dependency check that runs offline-tolerant, in CI or on a laptop, without granting a third-party service write access to the repository.
- **Not a target: a large organisation needing fleet-wide policy enforcement, SBOM attestation or licence compliance.** Those are different products.

## Goals
- G1 Find every dependency a project actually declares, including the ones hidden in Dockerfiles and CI workflow files.
- G2 Tell apart "unsafe" from "merely old", and fail only on unsafe.
- G3 Drop into an existing test suite with one file and no change to how the suite is run.
- G4 Work in any of the author's projects, Python or JavaScript, with the ecosystem readers the project needs and no dead weight from the ones it does not.
- G5 Be honest when it does not know: an unreachable registry is "unknown", never "clean".
- G6 Be presentable as a public tool: a stranger can install it, point it at their project and understand the output without reading the source.

## Non-goals
- **Never edits a dependency pin.** Not with a flag, not with a confirmation prompt. A tool that rewrites pins unattended is a different and riskier product. The furthest it will go is printing the exact edit it would make (`propose` mode, later).
- No pull requests, no bot account, no scheduled hosted service.
- No private registry support in v1. It needs credential handling and becomes an explicit opt-in feature or nothing.
- No licence compliance, no SBOM generation, no container image layer scanning.
- No attempt to judge whether a project is *reachable* by an advisory. It reports what the advisory databases say and leaves the judgement to the policy file.

## User stories

### Running the check
- **US-001** As a maintainer, I can run one command in a project and get a report of what is vulnerable, withdrawn, outdated and unpinned.
  - Given a project with pinned dependencies, when I run `stocktake`, then I see a report grouped worst-first, and the exit code is 0 when nothing is unsafe, 1 when something is, and 2 when the registries could not be reached.
- **US-002** As a maintainer, I can narrow the report to what needs action.
  - Given a report with all kinds of finding, when I run `stocktake --only vulnerable`, then only vulnerable and withdrawn releases are listed.
- **US-003** As a maintainer, I can read the report as JSON so another program can use it.
  - Given any project, when I run `stocktake --format json`, then stdout is a single JSON object with every finding, its status, its advisories and the version that fixes them.
- **US-004** As a maintainer in a hurry, I can get a one-line answer.
  - Given any project, when I run `stocktake --format summary`, then one line states the counts and the exit code still distinguishes safe from unsafe.
- **US-005** As a maintainer, I can point the check at a project other than the current one.
  - Given a path, when I run `stocktake --root <path>`, then that project is read and its own config file is used.

### Inside a test suite
- **US-010** As a maintainer, I can add the check to an existing pytest suite with one file and no change to how I run the suite.
  - Given a project with pytest, when I add the generated test file and run `pytest`, then the dependency check runs, fails only on unsafe findings, and reports outdated dependencies as warnings in the summary.
- **US-011** As a maintainer working offline or on a plane, the suite does not fail because of it.
  - Given no network, when I run the suite, then the dependency test is skipped with the reason, not failed.
- **US-012** As a maintainer, repeated test runs do not hammer the registries.
  - Given a check that ran less than six hours ago, when I run it again, then the answers come from the cache and no request is made.
- **US-013** As a maintainer of a project that cannot take a new dependency, I can vendor the checker into it.
  - Given any project, when I run `stocktake vendor <path>`, then a single self-contained Python file is written there that performs the same check with no installed dependency, and a guard test in StockTake proves that file behaves the same as the package.

### Deciding what to do
- **US-020** As a maintainer, I can accept a known advisory for a stated period with a stated reason.
  - Given an advisory I have assessed, when I add it to `ignore_advisories` in `.stocktake.toml` with a reason and an `until` date, then it stops failing the check until that date.
- **US-021** As a maintainer, I cannot let an accepted risk become permanent by forgetting it.
  - Given a policy entry whose `until` date has passed, when the check runs, then the check fails naming that entry, and the advisory it covered is reported again.
- **US-022** As a maintainer, I can hold a package back from an update on purpose without it showing as a problem.
  - Given a package in `hold_back`, when a newer release exists, then it is reported as `held` with my reason rather than `outdated`.
- **US-023** As a maintainer, a policy entry with no reason or no valid date is itself a failure.
  - Given an entry missing `reason` or with an unparseable `until`, when the check runs, then it fails naming what is missing.

### Reading the right things
- **US-030** As a maintainer, pins inside a Dockerfile are read, including across line continuations and through shell variables.
  - Given `RUN pip install a==1.0 \` continued onto further lines, and a GitHub release download whose tag is `${VERSION}`, when the project is scanned, then both are found with their versions resolved.
- **US-031** As a maintainer, the Python manifests a project may use are all read.
  - Given `pyproject.toml`, `requirements*.txt`, `uv.lock`, `poetry.lock` or `Pipfile.lock`, when the project is scanned, then the dependencies each declares are found, and `pyproject` entries are checked at the version actually installed in this environment where one is installed.
- **US-032** As a maintainer of a web project, npm dependencies are read and checked.
  - Given `package.json` with a lockfile, when the project is scanned, then the resolved versions are checked against the npm registry and against OSV's `npm` ecosystem.
- **US-033** As a maintainer, the versions pinned in my CI workflows and container base images are read.
  - Given `uses: owner/repo@ref` in a workflow and `FROM image:tag` in a Dockerfile, when the project is scanned, then each is compared with the newest release or tag.
- **US-034** As a maintainer, I am told when my project grows a kind of manifest the checker cannot read.
  - Given a project that gains `go.mod`, when the check runs, then it reports that manifest as unread rather than silently ignoring it, and the guard test fails until a reader exists or the file is excluded in config.
- **US-035** As a maintainer, I am told when the checker misses a pin that is plainly there.
  - Given a Dockerfile containing `name==version`, when the guard test counts those pins independently of the scanner, then the counts match or the test fails.
- **US-036** As a maintainer, a dependency declared as a range is resolved against my project's environment, or not at all.
  - Given a `pyproject.toml` declaring `flask>=2` and a project virtual environment holding Flask 3.0.0, when the project is scanned, then Flask is checked at 3.0.0.
  - Given no environment that can be found, when the project is scanned, then those dependencies are reported as unpinned and the report says no environment was found and how to name one — never resolved against a different environment, such as StockTake's own.
  - Given `--environment PATH`, when that path holds no environment, then the run stops with exit 2 rather than falling back to a guess.

### Configuring it per project
- **US-040** As a maintainer, each project says in one file which ecosystems to read, what to exclude and what has been decided.
  - Given `.stocktake.toml` at the project root, when the check runs, then only the listed ecosystems are read, the listed paths are skipped, and the policy in that file applies.
- **US-041** As a maintainer of a project that only needs part of the tool, nothing I did not ask for runs.
  - Given a config naming only `python`, when the check runs, then no npm, workflow or container reader runs and no npm registry request is made.

### Seeing it in CI
- **US-050** As a maintainer, CI can show findings against the exact lines they come from.
  - Given a CI run, when I run `stocktake --format sarif`, then the output is valid SARIF 2.1.0 with a result per finding located at its file and line.

## Scope (MoSCoW)

**Must have** (all done as of M1)
- Python readers: Dockerfile pip pins, `pyproject.toml`, `requirements*.txt`
- Registries: PyPI, OSV (PyPI ecosystem), GitHub releases
- Policy in `.stocktake.toml` with reason and expiry; overdue entries fail
- Text and JSON reports; exit codes 0/1/2
- `stocktake` CLI with `--only`, `--format`, `--root`, `--refresh`, `--all-advisories`
- pytest plugin with the fail/warn/skip rules, **off until a project asks for it** ([ADR 0007](adr/0007-the-pytest-plugin-is-opt-in.md))
- Guard tests: missed-pin count, unread-manifest detection
- Six-hour shared cache; offline means unknown

**Should have**
- ~~Python lockfile readers: `uv.lock`, `poetry.lock`, `Pipfile.lock`~~ (done, M1, plus `pdm.lock` and `Pipfile`)
- npm reader plus registry.npmjs.org and OSV `npm`
- GitHub Actions `uses:` pins; Docker `FROM` tags and digests
- SARIF output; `--format summary`
- `stocktake vendor` single-file copy with its guard tests
- A GitHub Actions workflow in this repo running its own check

**Could have**
- Go (`go.mod`, proxy.golang.org, OSV `Go`) and Rust (`Cargo.toml`/`Cargo.lock`, crates.io, OSV `crates.io`)
- `propose` mode printing the exact edit and a compare link, never applying it
- pre-commit hook pins; apt packages named in Dockerfiles
- Strictness flag making a major-version gap a failure for projects that want it
- Scheduled run writing a report to a file or a notification

**Will not have**
- Applying updates, opening pull requests, private registries in v1, SBOM, licence scanning

## Non-functional requirements
- **NFR-1 Privacy.** Only package names and versions leave the machine, to pypi.org, registry.npmjs.org, api.github.com and api.osv.dev. No telemetry, no project paths, no file contents, ever.
- **NFR-2 Dependency weight.** The core runs on the Python standard library alone. `packaging` is used for version comparison when importable and falls back to a built-in comparison when not. Dev dependencies (pytest, ruff, mypy) are not needed to run the check.
- **NFR-3 Read-only.** The tool opens no file for writing inside the project it checks, and leaves no handle open. The only files it writes are its own cache and whatever `vendor` is explicitly asked to create.
- **NFR-4 Determinism in tests.** No test touches the real network, clock or filesystem outside `tmp_path`, except the one test marked `network`, which is skipped rather than failed when the registries are unreachable.
- **NFR-5 Speed.** A cached run of a project with a few hundred dependencies finishes in under two seconds. An uncached run makes registry requests concurrently and politely, with one identifying User-Agent.
- **NFR-6 Platforms.** Works on Windows, macOS and Linux, on Python 3.11 and later.
- **NFR-7 Honesty of output.** Report text says "no known advisories", never "safe". A registry timeout is reported as unknown and never counted as clean.

## Success metrics
- The check is still enabled in every project it was added to three months later (the real metric; the tool failing on "old" is what kills it).
- First run on a project the author believed to be current finds at least one thing worth acting on.
- False positives found in use are fixed and get a regression test; the count trends to zero.
- A stranger can go from `uv tool install stocktake` to a readable report in under five minutes using the README alone.

## Assumptions
- The projects it checks are small enough that scanning the whole tree is cheap once obvious folders are excluded.
- OSV coverage is good enough for PyPI and npm to be worth acting on, and poor for GitHub release binaries, which therefore get "newest tag" only.
- Package names and versions are not sensitive for the author's projects. Projects where even that is sensitive should not use the network features.
- The author's own `ai-suite` repository stays the reference consumer and is not modified as part of building this.

## Risks
- **R1 False positives destroy trust faster than false negatives.** Mitigation: fail only on vulnerable or withdrawn, everything else warns or is listed; every false positive found gets a regression test.
- **R2 Advisory noise.** A single package returned 90 OSV entries. Mitigation: merge aliases, rank by severity, show the worst five and a count, and name the single version that clears them all.
- **R3 Registry rate limits.** GitHub allows 60 anonymous requests an hour. Mitigation: six-hour shared cache, concurrency cap, optional `GITHUB_TOKEN`, and one rate-limited answer becoming `unknown` without poisoning the rest of the run.
- **R4 Scanner silently missing pins.** The most dangerous failure, because the report looks clean. Mitigation: guard tests that count pins independently of the scanner, and an unread-manifest check that fails on a manifest kind with no reader.
- **R5 Reader sprawl.** Eight ecosystems is a lot of registry clients to keep working. Mitigation: a narrow reader interface, one guard test per reader, and ecosystems enabled per project so unused ones never run.
- **R6 Version comparison differs by ecosystem.** SemVer, PEP 440 and bare integers do not sort alike. Mitigation: comparison is per-ecosystem behind one function, with the odd cases as test cases.
- **R7 A public tool invites expectations.** Issues, platform reports, feature requests. Mitigation: non-goals stated in the README, and no promise of support.

## Open questions
- Should `outdated` ever be allowed to fail, behind a strictness flag, for a project that wants to stay current? (Leaning yes, off by default, decided when a project asks for it.)
- Does the shared cache at `~/.cache/stocktake/` need locking once several projects run the check concurrently in CI?
- Is `stocktake` the right name to publish on PyPI (it is free as of 2026-10-29), and should publishing wait until there are two real consumers?
- For npm, should the check read the lockfile's resolved versions only, or also flag a `package.json` range that permits a vulnerable version?

## Glossary
- **Dep** — one dependency as a project declares it: ecosystem, name, version (pinned or installed), the file and line it came from, the specifier as written, and its role.
- **Ecosystem** — the registry a name belongs to: `PyPI`, `npm`, `GitHub`, `Docker`.
- **Reader** — the part that turns one kind of manifest into Deps.
- **Registry client** — the part that answers "what is the newest version of this" and "are there advisories against this version".
- **Finding** — a Dep plus a judgement: its status and severity.
- **Status** — `vulnerable`, `yanked`, `outdated`, `held`, `current`, `unpinned`, `unknown`.
- **Severity** — what the status means for the build: `fail`, `warn`, `info`, `ok`.
- **Yanked / withdrawn** — a release its own author retracted.
- **Advisory** — a published security report against a version range, from OSV.
- **Policy** — the decisions recorded in `.stocktake.toml`: advisories accepted for now, packages held back; each with a reason and an expiry.
- **Held** — outdated, and deliberately so, per policy.
- **Unpinned** — declared with no fixed version, so what gets installed depends on when.
- **Guard test** — a test that checks the checker itself did not miss something, by counting independently of the code under test.
