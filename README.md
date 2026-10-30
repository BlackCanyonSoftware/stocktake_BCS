# StockTake

**A stock-take of what your project depends on.** It reads what the project pins, asks the public registries whether a newer release exists and whether the pinned one has a known security advisory, and fails your tests only when something is actually unsafe.

It never edits a file. It needs no account, no bot, no repository access. It sends nothing but package names and versions.

Think of it as a dependency check you run yourself, inside your own test suite, on whatever you are working on right now.

```bash
uv tool install stocktake   # or: pipx install stocktake
stocktake
```

## Why not Dependabot or Renovate?

They are good, and this is not trying to replace them. It exists because of the gaps:

| | Dependabot / Renovate | StockTake |
|---|---|---|
| Needs a hosted repository | yes | no — it runs wherever you are |
| Opens pull requests | yes, on its own schedule | never; it reports and nothing else |
| Sees `RUN pip install name==1.2.3` in a Dockerfile | no | **yes** |
| Sees a binary fetched from a GitHub release | no | yes (newest tag only) |
| Checks the version actually installed in your dev environment | no | yes |
| Runs in your test suite, offline-tolerant | no | yes |
| Fails your build for being behind | configurable, often yes | **never** — only unsafe findings fail |

That last row is the design. A check that fails the build because a dependency is four months behind gets switched off within a week, and then it protects nothing.

## What it reads

**Python**
- pip pins inside Dockerfiles — `pip install`, `uv pip install`, `uv tool install`, `pipx install` — across backslash line continuations and past options that take an argument
- `pyproject.toml`: `dependencies`, every `optional-dependencies` group, and PEP 735 `dependency-groups`, each checked at the version **actually installed** in the current environment where there is one
- unpinned installs, reported as unpinned rather than skipped

**Binaries**
- GitHub release downloads in Dockerfiles, resolving `${VERSION}` against the nearest earlier assignment, compared with the newest release tag

It asks [PyPI](https://pypi.org) for the newest release and for withdrawn ones, the GitHub releases API for the newest tag, and [OSV](https://osv.dev) for advisories against the exact version in use.

**Not read yet:** `requirements*.txt`, lockfiles, npm, GitHub Actions pins, container base images, Go, Rust. These are coming (see [docs/ROADMAP.md](docs/ROADMAP.md)) — and until a reader exists, a manifest of that kind is reported as **unread** rather than silently ignored, so you are never shown a clean report that quietly skipped half your project.

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

Exit codes: **0** nothing unsafe, **1** something unsafe, **2** the check could not be completed (registries unreachable, or the config could not be read). A registry that times out is `unknown` — never "clean".

## What it looks like

A real run against a project pinning `pillow==9.0.0` and `requests==2.19.1`:

```text
Dependency check 2026-10-30: 5 checked, 2 vulnerable, 0 withdrawn, 1 outdated, 1 unpinned

VULNERABLE (fix these)
  Dockerfile:3    pillow 9.0.0  52 advisories (6 critical, 32 high, 12 moderate, 2 unrated); upgrade to 13.0.0 or newer
      GHSA-332p-7hrc-92wf CRITICAL: Pillow: Heap buffer overflow in _tiffWriteProc when saving TIFF to BytesIO
      GHSA-3f63-hfp8-52jq CRITICAL: Arbitrary Code Execution in Pillow
      GHSA-5x8w-8jj5-q52h CRITICAL: Pillow: Heap buffer overflow in FlashPix (FPX) JPEG decoding leads to code execution
      GHSA-8g5g-8vmr-9782 CRITICAL: Pillow: Heap buffer overflow in ImagingJpegDecode
      GHSA-8vj2-vxx3-667w CRITICAL: Arbitrary expression injection in Pillow
      ... and 47 more (stocktake --only vulnerable --all-advisories)
  Dockerfile:3    requests 2.19.1  5 advisories (1 high, 4 moderate); upgrade to 2.33.0 or newer
      GHSA-x84v-xcm2-53pg HIGH: Insufficiently Protected Credentials in Requests
      GHSA-9hjg-9r4m-mvj7 MODERATE: Requests vulnerable to .netrc credentials leak via malicious URLs
      GHSA-9wx4-h78v-vm56 MODERATE: Requests `Session` object does not verify requests after making first request with verify=False
      GHSA-gc5v-m9x4-r6x2 MODERATE: Requests has Insecure Temp File Reuse in its extract_zipped_paths() utility function
      GHSA-j8r2-6x86-q33q MODERATE: Unintended leak of Proxy-Authorization header in requests

OUTDATED
  Dockerfile:9    mostlygeek/llama-swap 262 -> 268 (major)

UNPINNED
  Dockerfile:3    ruff (none)  no version is pinned: whatever is newest when the image is built

CURRENT: 1 up to date
```

Advisory lists are merged and ranked, because raw ones are unreadable: one real package returned ninety OSV entries for a single pinned version. Aliases of the same problem (a GHSA and its PYSEC twin) become one entry, the worst five are shown with a count of the rest, and the single version that clears them all is named.

## Deciding to live with something

Put the decision in `.stocktake.toml` at the project root. Every entry needs a reason and a date to look at it again — and **an entry past its date fails the check** until you decide again, so "ignore it for now" cannot become permanent by neglect. That is what makes the escape hatch safe to use.

```toml
# .stocktake.toml
exclude = ["vendor", "tests/fixtures"]

[[policy.ignore_advisories]]
id = "GHSA-xxxx-xxxx-xxxx"
reason = "only reachable through a feature we do not use"
until = 2026-12-01

[[policy.hold_back]]
package = "pillow"
reason = "12.4 changes the PNG writer; rebuild the logo samples first"
until = 2026-12-01
```

A Python project that would rather not have another file can use a `[tool.stocktake]` table in `pyproject.toml` instead. If both exist, `.stocktake.toml` wins.

## Commands

```bash
stocktake                           # the full report
stocktake --only vulnerable         # just what must be fixed
stocktake --only outdated           # what must be fixed, then what is behind
stocktake --format json             # for another program
stocktake --refresh                 # ignore the six-hour cache
stocktake --root ../other-project   # check a different project
stocktake --all-advisories          # every advisory, not the worst five
```

`stocktake --help` is the full reference. `python -m stocktake` works too.

## Using it from Python

```python
from pathlib import Path
from stocktake import Registries, evaluate, load_config, render_text, scan

root = Path(".")
config = load_config(root)
report = evaluate(scan(root, config), Registries(), config.policy)

print(render_text(report))
assert not report.failed
```

A pytest plugin that wraps this up as one test — warning on outdated, skipping when offline — is the next milestone. Until then the five lines above in a test file do the job.

## Privacy and what it touches

- **Sent:** package names and versions, to `pypi.org`, `api.github.com` and `api.osv.dev`. Nothing else. No paths, no file contents, no telemetry.
- **Written:** one cache file (`%LOCALAPPDATA%\stocktake\cache.json` on Windows, `~/.cache/stocktake/cache.json` elsewhere; `STOCKTAKE_CACHE` overrides it). Nothing inside the project it checks, ever.
- **Executed:** nothing it found. It does not import a scanned package, run a lockfile's scripts, or shell out to a package manager.
- Answers are cached for six hours and shared across projects, so repeated test runs are fast and the public services are not hammered.
- Set `GITHUB_TOKEN` to raise GitHub's anonymous limit of 60 requests an hour. It is sent to GitHub alone.

## Install

Requires Python 3.11 or later. **The core has no dependencies at all** and never will — a tool whose job is watching your supply chain is a poor advertisement for itself if adopting it widens that supply chain. (`packaging` is used for version comparison when it happens to be importable, and has a built-in fallback when it is not.)

```bash
uv tool install stocktake          # as a command
uv add --dev stocktake             # as a dev dependency of a project
pip install stocktake
```

From a clone, for development:

```bash
py -3.11 -m venv .venv
./.venv/Scripts/python -m pip install -e ".[dev]"   # .venv/bin/python on macOS and Linux
./.venv/Scripts/python -m pytest
```

## Non-goals

Stated plainly, because they are decisions and not omissions:

- **It will never edit a dependency pin.** Not with a flag, not with a confirmation. A tool that rewrites pins unattended is a different and riskier product. The furthest it will go is printing the exact edit it would make.
- No pull requests, no bot account, no hosted service.
- No private registries in v1. That needs credential handling, and would be an explicit opt-in or nothing.
- No SBOM generation, no licence compliance, no container image layer scanning.
- It does not judge whether an advisory is actually reachable in your code. It reports what the databases say; the policy file is where your judgement goes.

## Documentation

| | |
|---|---|
| [docs/PRD.md](docs/PRD.md) | what it is for, the user stories, the non-functional requirements |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | the shape, the module boundaries, how to add an ecosystem |
| [docs/DESIGN.md](docs/DESIGN.md) | the report layout, statuses, exit codes, output states |
| [docs/ROADMAP.md](docs/ROADMAP.md) | what is built and what is next |
| [docs/adr/](docs/adr/) | why it is built this way |
| [docs/HANDOFF.md](docs/HANDOFF.md) | current state, for picking the work back up |

## Licence

MIT. See [LICENSE](LICENSE).
