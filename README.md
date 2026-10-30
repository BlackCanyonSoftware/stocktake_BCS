# StockTake

**A stock-take of what your project depends on.** It reads what the project pins, asks the public registries whether a newer release exists and whether the pinned one has a known security advisory, and fails your tests only when something is actually unsafe.

It never edits a file. It needs no account, no bot, no repository access. It sends nothing but package names and versions.

Think of it as a dependency check you run yourself, inside your own test suite, on whatever you are working on right now.

```text
Dependency check 2026-10-30: 392 checked, 3 vulnerable, 0 withdrawn, 192 outdated, 0 unpinned

VULNERABLE (fix these)
  package-lock.json    electron 44.9.0  1 advisory (1 high); upgrade to 44.9.1 or newer
      GHSA-jr5w-w6x2-84p9 HIGH: Electron: Mitigation for compromised eMudhra intermediate certificates
  package-lock.json    fast-uri 3.1.8  4 advisories (2 moderate, 2 low); upgrade to 3.1.9 or newer
      GHSA-w74x-v6f9-j3xg MODERATE: fast-uri vulnerable to URI scheme spoofing via percent-encoded scheme decoding
```

Exit codes: **0** nothing unsafe · **1** something unsafe · **2** the check could not be completed.

---

## Install

> **StockTake is not published anywhere yet.** `pip install stocktake` and `uv tool install stocktake` do **not** work — the name is unclaimed on PyPI by choice, not by accident. Install from a clone. The two commented lines below are what to use once it is published; nothing else about using it changes.

```bash
git clone https://github.com/BlackCanyonSoftware/stocktake_BCS.git
cd stocktake_BCS
py -3.11 -m venv .venv                                   # python3.11 -m venv on macOS and Linux
./.venv/Scripts/python -m pip install -e .                # .venv/bin/python elsewhere
./.venv/Scripts/stocktake --version

# Once published, instead of all of the above:
#   uv tool install stocktake        # as a command, anywhere
#   uv add --dev stocktake           # as a dev dependency of one project
```

Requires **Python 3.11 or later** and nothing else. The core has no dependencies at all and never will — a tool whose job is watching your supply chain is a poor advertisement for itself if adopting it widens that supply chain. (`packaging` is used for version comparison when it happens to be importable, with a built-in fallback when it is not.)

**Installing from git** (`pip install git+https://github.com/BlackCanyonSoftware/stocktake_BCS`) works, but check what is actually on the default branch first: as of this writing the branch is several commits behind the local work, and an install from it would be missing the pytest plugin and the npm reader entirely.

---

## Adding it to a project

Pick the row that matches the project. Each one is complete — you do not need the others.

| The project… | Do this | Needs StockTake installed? |
|---|---|---|
| runs **pytest** | one line in its pytest config | yes, as a dev dependency |
| is **Python**, and you want to own the test file | `stocktake init` | yes, as a dev dependency |
| **cannot take a dependency**, or is not Python at all | `stocktake vendor` | no — this is what it is for |
| is **anything**, and you want it checked in CI | a CI step | yes, in the CI job |
| you only want to **look once** | `stocktake --root PATH` | yes, anywhere |

### 1. A project that runs pytest — one line

Add StockTake to the project's dev dependencies, then one line to wherever it configures pytest:

```toml
# pyproject.toml
[tool.pytest.ini_options]
stocktake = true
```

That is the whole change. `pytest` now runs the dependency check with the rest of the suite:

```text
tests/test_the_projects_own_thing.py ..                                  [ 66%]
stocktake_dependency_check PASSED                                        [100%]

============================== warnings summary ===============================
  DependencyUpdateAvailable: 1 dependencies have a newer release: click 8.1.7->8.5.0

======================== 3 passed, 1 warning in 1.15s =========================
```

Wherever the project already configures pytest works just as well — mind the section name, which is pytest's own rule rather than StockTake's:

| File | Section |
|---|---|
| `pyproject.toml` | `[tool.pytest.ini_options]` |
| `pytest.ini` | `[pytest]` |
| `tox.ini` | `[pytest]` |
| `setup.cfg` | `[tool:pytest]` — `[pytest]` here is an error pytest refuses |

**Installing StockTake on its own changes nothing** about any test run until a project asks for it like this. That is deliberate ([ADR 0007](docs/adr/0007-the-pytest-plugin-is-opt-in.md)): a dependency that silently added a network-touching test to somebody's suite would be a bad guest.

| | |
|---|---|
| `--stocktake` | switch it on for one run without editing anything |
| `--no-stocktake` | switch it off for one run (a plane, a locked-down runner) |
| `-m "not stocktake"` | deselect it like any other marked test |
| `STOCKTAKE_OFFLINE=1` | force the skip, for a build that must not touch the network |

### 2. A Python project, owning the test file

```bash
cd /path/to/the/project
stocktake init
```

Writes two files and overwrites nothing:

- `tests/test_dependencies.py` — four lines, yours to edit afterwards
- `.stocktake.toml` — every option, commented out, so a fresh config behaves exactly like no config

Use this instead of the plugin when you would rather see the check in the repository than infer it from a config line.

### 3. A project that cannot take a dependency — one file, nothing to install

```bash
cd /path/to/the/project
stocktake vendor .
```

Writes `stocktake_vendored.py`: the whole core as one self-contained file, standard library only. Then:

```python
from pathlib import Path
import stocktake_vendored as stocktake

report = stocktake.run_check(Path("."))

if stocktake.skip_reason(report):           # registries unreachable: not a failure
    ...
if stocktake.update_warning(report):        # a newer release exists: a warning, never a failure
    ...
assert stocktake.failure_text(report) is None
```

This is the route for a Node project, a Dockerfile-only repository, or anywhere a new Python dependency is not welcome. It is generated from the package, so refresh it by running `stocktake vendor` again rather than editing it. It does **not** include the pytest plugin, `stocktake init`, or the command line — a single file cannot carry those.

### 4. Any project, checked in CI

```yaml
- uses: actions/setup-python@v7
  with:
    python-version: "3.13"
- run: pip install git+https://github.com/BlackCanyonSoftware/stocktake_BCS
- run: stocktake --format sarif > stocktake.sarif || true
- uses: github/codeql-action/upload-sarif@v4
  with:
    sarif_file: stocktake.sarif
```

The `|| true` is deliberate: exit 1 means it found something, which is exactly what there is to upload. The findings then appear in the repository's code-scanning view on the lines they came from. Set `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` on the steps to raise GitHub's anonymous limit of 60 requests an hour. The job needs `permissions: security-events: write`.

For a project with no Python in it at all, this plus the vendored file are the two routes — and the vendored file needs no install step.

### 5. Just look

```bash
stocktake --root /path/to/the/project
```

Changes nothing, writes nothing in that project, and tells you where it stands. Start here.

---

## If you are an AI assistant adding this to a project

The decision is just the table above; the traps are these.

1. **Check how the project tests itself first.** `stocktake = true` only works if the project actually runs pytest. A Node project, or a Django project using `manage.py test`, needs route 3 or 4 — not route 1. Getting this wrong produces a config line that silently does nothing.
2. **Do not change any dependency pin as part of adopting it.** StockTake reports; acting on a report is a separate, reviewed change.
3. **`stocktake init` and `stocktake vendor` write files.** `init` refuses to overwrite without `--force`; `vendor` always overwrites, because refreshing the generated file is the point. Neither touches anything else.
4. **Expect exit 1 on the first run of a real project.** It means it found something, not that the setup is broken. All five projects it has been run against had vulnerable dependencies.
5. **A project whose Python environment is not `./.venv`** needs `--environment PATH`, or an `environment` line in `.stocktake.toml`. Without it, dependencies declared as a range are reported as unpinned rather than checked — honestly, but uselessly. The report says so when this happens, and names the flag.
6. **A project with no `node_modules`** has its `package.json` ranges unresolved for the same reason. Run the install first, or read the lock file findings, which are unaffected.
7. **Do not add `stocktake` to a project's *runtime* dependencies.** It is a development tool.
8. **The cache** lives outside the project (`%LOCALAPPDATA%\stocktake` or `~/.cache/stocktake`). Nothing needs adding to `.gitignore`.
9. **Read [AGENTS.md](AGENTS.md) instead of this section** if you are changing StockTake itself rather than using it. Different job, different rules.

---

## Configuring it

One file at the project root, or a `[tool.stocktake]` table in `pyproject.toml`. Every key is optional, and a project with no config at all behaves sensibly. `stocktake init` writes this with everything commented out.

```toml
# .stocktake.toml
ecosystems = ["python", "npm"]   # which readers to run; default: all
                                 # (python, npm, workflows, binaries)
exclude = ["vendor", "tests/fixtures"]
accept_unread = ["go.mod"]       # "I know you cannot read this yet": stops the notice, stays in the JSON
environment = "tools/env"        # where this project's Python environment is, if not ./.venv

[cache]
ttl_hours = 6

# Decisions you have made. Each needs a reason and a date to make it again:
# an entry past its `until` date FAILS the check until it is renewed, so
# "ignore it for now" cannot quietly become "ignore it forever".

[[policy.ignore_advisories]]
id = "GHSA-xxxx-xxxx-xxxx"
reason = "only reachable through a feature we do not use"
until = 2026-12-01

[[policy.hold_back]]
package = "pillow"
reason = "12.4 changes the PNG writer; rebuild the logo samples first"
until = 2026-12-01
```

Every value is validated as it is read. An unknown ecosystem name is **refused**, not ignored — a typo that silently switched half the check off would be the worst kind of failure for a file like this. If both files exist, `.stocktake.toml` wins and the report says which was used.

---

## Commands

```bash
stocktake                              # the full report
stocktake --only vulnerable            # just what must be fixed
stocktake --only outdated              # what must be fixed, then what is behind
stocktake --format summary             # one line, for a status bar or a CI step name
stocktake --format json                # for another program
stocktake --format sarif               # for an editor, or GitHub code scanning
stocktake --refresh                    # ignore the six-hour cache
stocktake --root ../other-project      # check a different project
stocktake --environment /path/to/venv  # resolve ranges against this environment
stocktake --all-advisories             # every advisory, not the worst five
stocktake init                         # write the check into this project's test suite
stocktake vendor .                     # write the core as one self-contained file
```

`stocktake --help`, `stocktake init --help` and `stocktake vendor --help` are the full reference. `python -m stocktake` works too.

### Using it from Python

```python
from pathlib import Path
from stocktake.check import failure_text, run_check, skip_reason, update_warning

report = run_check(Path("."))

print(f"{len(report.findings)} checked, {report.counts['vulnerable']} vulnerable")
assert failure_text(report) is None
```

`run_check` does the lot: reads the config, finds the environment, scans, asks the registries and judges the answers. `scan`, `evaluate`, `render_text`, `render_sarif` and `Registries` are all exported from `stocktake` if you want to drive the pieces yourself.

---

## What it reads

**Python** (the `python` ecosystem)
- pip pins inside Dockerfiles — `pip install`, `uv pip install`, `uv tool install`, `pipx install` — across backslash line continuations and past options that take an argument
- `requirements*.txt` and `constraints*.txt`, through continuations, `--hash=` digests, `-r`/`-e`/`--index-url` options and direct `name @ url` references
- lock files: `uv.lock`, `pdm.lock`, `poetry.lock`, `Pipfile.lock` — the project's own package skipped, since no registry has it
- `pyproject.toml`: `dependencies`, every `optional-dependencies` group, and PEP 735 `dependency-groups`
- `Pipfile`: `packages` and `dev-packages`

**JavaScript** (the `npm` ecosystem)
- `package.json`: all four dependency sections, past the values that are not registry versions at all (`file:`, `git+`, `workspace:`, `npm:` aliases, `owner/repo` shorthand)
- `package-lock.json`, both the modern flat layout and the old nested one, skipping the project itself, its workspaces and its links
- ranges resolved against what is actually in `node_modules`, including dependencies hoisted to the top of a workspace

**CI** (the `workflows` ecosystem)
- `uses: owner/repo@ref` in `.github/workflows/*.yml` and `action.yml`, including reusable workflows
- a full version tag is a pin; `@v7` is a **moving tag**, so only a major change counts as an update ([ADR 0008](docs/adr/0008-a-tag-its-publisher-moves-is-a-range.md)); a commit SHA takes its version from the conventional `# v4.1.1` comment beside it, and says so when there isn't one

**Binaries** (the `binaries` ecosystem)
- GitHub release downloads in Dockerfiles, resolving `${VERSION}` against the nearest earlier assignment

It asks [PyPI](https://pypi.org) for the newest release and for withdrawn ones, [npm](https://registry.npmjs.org) and the GitHub releases API for the newest version, and [OSV](https://osv.dev) for advisories against the exact version in use.

### Pins, ranges, and which version gets checked

- **A file that pins a version is checked at its pin** — a Dockerfile `==`, a lock file, a `requirements.txt` line with `==`, a bare `1.2.3` in `package.json`. That is what will be installed.
- **A file that declares a range** — `pyproject.toml`, `Pipfile`, `requirements.txt` with `>=`, `package.json` with `^1.2.3` — says nothing about what is running, so it is checked at the version **actually installed**: the project's Python environment, or its `node_modules`.

StockTake looks for the Python environment in this order: one you name with `--environment`, then the project's own `.venv` or `venv`, then the environment active in your shell when you are checking the current directory. If it cannot find one it says so and reports those dependencies as unpinned — it will not resolve them against some *other* environment, such as its own ([ADR 0006](docs/adr/0006-which-environment-an-installed-version-comes-from.md)).

**Not read yet:** container base images, `yarn.lock` and `pnpm-lock.yaml` (both need a YAML parser, and the core has no dependencies — but a yarn or pnpm project is still checked through its `package.json` and `node_modules`), Go, Rust, conda, pre-commit hooks. See [docs/ROADMAP.md](docs/ROADMAP.md) — and until a reader exists, a manifest of that kind is reported as **unread** rather than silently ignored, so you are never shown a clean report that quietly skipped half your project.

---

## What it does with what it finds

| Finding | Meaning | Your build |
|---|---|---|
| `vulnerable` | an advisory affects the version in use | **fails** |
| `yanked` | the author withdrew this release | **fails** |
| policy entry past its date | a decision you deferred has come due | **fails** |
| `outdated` | a newer release exists | a warning in the test summary — never a failure |
| `held` | outdated on purpose, per your policy, until a date | listed |
| `unpinned` | no version fixed, so what installs depends on when | listed |
| `unknown` | not found, or that one answer could not be had | listed |
| `current` | newest release, no known advisories | counted |

**Being behind is not a failure.** A check that fails the build because a dependency is four months behind gets switched off within a week, and then it protects nothing. That is the decision the whole tool rests on ([ADR 0004](docs/adr/0004-only-unsafe-findings-fail-the-build.md)), and "it would be more thorough to fail on X" has been considered and rejected.

A registry that times out is `unknown` — never "clean". Advisory lists are merged and ranked, because raw ones are unreadable: one real package returned 90 OSV entries for a single pinned version. Aliases of the same problem become one entry, the worst five are shown with a count of the rest, and the single version that clears them all is named.

---

## Why not Dependabot or Renovate?

They are good, and this is not trying to replace them. It exists because of the gaps:

| | Dependabot / Renovate | StockTake |
|---|---|---|
| Needs a hosted repository | yes | no — it runs wherever you are |
| Opens pull requests | yes, on its own schedule | never; it reports and nothing else |
| Sees `RUN pip install name==1.2.3` in a Dockerfile | no | **yes** |
| Sees a binary fetched from a GitHub release | no | yes (newest tag only) |
| Checks the version actually installed in your dev environment | no | yes |
| Checks your GitHub Actions pins | yes | yes |
| Runs in your test suite, offline-tolerant | no | yes — one line of config |
| Fails your build for being behind | configurable, often yes | **never** — only unsafe findings fail |

### Checked against `npm audit`

On a real 392-package project, StockTake and `npm audit` agreed exactly: the same two vulnerable packages, the same severities, the same four advisories on one of them. StockTake also named the versions that fix them, which `npm audit` only reports as "a fix is available".

Two differences worth knowing in general:

- **StockTake counts findings; `npm audit` counts packages.** A package declared in both `package.json` and `package-lock.json` is two findings, at two source locations, because fixing it means editing both.
- **`npm audit` also reports packages affected only *through* a dependency.** StockTake reports the vulnerable package itself, with the advisory against it.

---

## Privacy and what it touches

- **Sent:** package names and versions, to `pypi.org`, `registry.npmjs.org`, `api.github.com` and `api.osv.dev`. Nothing else. No paths, no file contents, no telemetry.
- **Written:** one cache file (`%LOCALAPPDATA%\stocktake\cache.json` on Windows, `~/.cache/stocktake/cache.json` elsewhere; `STOCKTAKE_CACHE` overrides it). Nothing inside the project it checks, ever — except the files `init` and `vendor` are explicitly asked to write.
- **Executed:** nothing it found. It does not import a scanned package, run a lockfile's scripts, or shell out to a package manager.
- Answers are cached for six hours and shared across projects, so repeated test runs are fast and the public services are not hammered. A failed *connection* is retried once; a service that answered is not.
- Set `GITHUB_TOKEN` to raise GitHub's anonymous limit of 60 requests an hour. It is sent to GitHub alone.

---

## Does it work?

It has been run against five real projects — Python, Node, and mixed — totalling about two thousand dependencies.

- On a 392-package Node project it agreed **exactly** with `npm audit`, as above.
- Across the five it found vulnerable dependencies in every one, including `tar 6.2.1` with 12 advisories (one critical) and an `electron` with 46.
- It found three of its own bugs that way, and only that way: ranges resolved against the wrong environment, a moving tag reported as outdated, and advice aimed at the wrong ecosystem. Each is fixed, each has a regression test, and the two that were decisions rather than slips are written up in [docs/adr/](docs/adr/).

Which is the honest summary: **the false positives in this tool were found by using it, not by designing it**, so if you find another one, that is the expected way for it to improve.

---

## Non-goals

Stated plainly, because they are decisions and not omissions:

- **It will never edit a dependency pin.** Not with a flag, not with a confirmation. A tool that rewrites pins unattended is a different and riskier product. The furthest it will go is printing the exact edit it would make.
- No pull requests, no bot account, no hosted service.
- No private registries yet. That needs credential handling, and would be an explicit opt-in or nothing.
- No SBOM generation, no licence compliance, no container image layer scanning.
- It does not judge whether an advisory is actually reachable in your code. It reports what the databases say; the policy file is where your judgement goes.

---

## Documentation

| | |
|---|---|
| [AGENTS.md](AGENTS.md) | for a person or AI **changing StockTake itself** |
| [CONTRIBUTING.md](CONTRIBUTING.md) | setting up, the boundaries, how to add an ecosystem, what must never change |
| [CHANGELOG.md](CHANGELOG.md) | what changed |
| [docs/PRD.md](docs/PRD.md) | what it is for, the user stories, the non-functional requirements |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | the shape, the module boundaries, how to add an ecosystem |
| [docs/DESIGN.md](docs/DESIGN.md) | the report layout, statuses, exit codes, output states |
| [docs/ROADMAP.md](docs/ROADMAP.md) | what is built and what is next |
| [docs/adr/](docs/adr/) | why it is built this way, including where a first attempt was wrong |
| [docs/HANDOFF.md](docs/HANDOFF.md) | current state, for picking the work back up |

## Licence

MIT. See [LICENSE](LICENSE). Contributions are welcome; [CONTRIBUTING.md](CONTRIBUTING.md) says how the pieces fit and which rules are not up for negotiation.

StockTake is made by [Black Canyon Software](https://blackcanyonsoftware.com).
