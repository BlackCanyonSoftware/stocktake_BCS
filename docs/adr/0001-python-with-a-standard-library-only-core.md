# ADR 0001: Python 3.11+ with a standard-library-only core

- **Date:** 2026-10-29
- **Status:** accepted

## Context
StockTake has to install into other people's projects and run inside their test suites. Whatever it depends on, they depend on. It also has to be defensible: a tool whose job is watching the supply chain is a poor advertisement for itself if adopting it widens that supply chain.

The existing implementation in `ai-suite` is already close to this: about 500 lines using only `urllib`, `json`, `tomllib`, `shlex`, `re`, `hashlib`, `concurrent.futures` and `dataclasses`, with `pyyaml` needed only for the optional policy file and `packaging` used opportunistically for version comparison.

Python was never really in question — the projects this must run in are Python, the existing code is Python, and pytest integration is a requirement. The real decisions are the minimum version and how strict to be about dependencies.

## Options considered

**A. Python 3.11+, standard library only at runtime.** `tomllib` arrived in 3.11, which removes the last reason to depend on anything: config and policy parse with no third party. `packaging` is imported inside a `try` for correct PEP 440 comparison and falls back to a built-in comparison when absent, and is never declared as a dependency.

**B. Python 3.9+ with a TOML dependency.** Reaches two more Python versions, at the cost of depending on `tomli`, or on YAML, or on carrying a copy of someone else's parser. Nothing the author runs needs 3.9 or 3.10.

**C. Python 3.11+ with a comfortable dependency set** (`httpx`, `pydantic`, `tomli-w`, `rich`). Faster and pleasanter to write. But `rich` means colour and box drawing, which DESIGN.md rules out for output that lands in pytest summaries and CI logs; `pydantic` is a large dependency for validating two config tables; and `httpx` buys retries and connection pooling that `urllib` plus an eight-way thread pool already covers for a few dozen requests.

**D. A compiled language (Go or Rust) distributed as one binary.** Genuinely attractive for a tool meant to drop into any project, and it would remove the Python-version question entirely. Rejected because the pytest plugin is a core requirement (US-010), the working implementation is Python, and nothing else the author maintains is in Go or Rust, so every change would cost more.

## Decision
Option A. Python 3.11 or later. The runtime core imports nothing outside the standard library. `packaging` stays a soft optional behind a `try`/`except`. Development dependencies (pytest, ruff, mypy, pre-commit) are declared in an optional `dev` group and are not needed to run the check.

Build backend hatchling with PEP 621 metadata and a `src/` layout; `uv` as the development and installation path (`uv tool install stocktake`).

## Consequences
- **Good.** One `uv tool install` with nothing behind it. Adding StockTake to a project adds no transitive dependency at all. The check keeps working in an environment too broken to install anything.
- **Good.** Nothing to keep up to date, which is the right posture for this particular tool.
- **Cost.** HTTP handling is written by hand: timeouts, the 403/429 versus 5xx distinction, JSON bodies. It is roughly forty lines and already written and tested, but it is ours to maintain.
- **Cost.** Version comparison without `packaging` is approximate for pre-releases. Mitigated by making comparison per-ecosystem (M3) with the awkward cases as test cases, and by `packaging` being present in most real environments anyway.
- **Cost.** No colour or progress output, ever, without taking a dependency. This is also [ADR 0004](0004-only-unsafe-findings-fail-the-build.md)'s and DESIGN.md's preference, so it costs nothing in practice.
- **Constraint accepted.** Python 3.10 and earlier are not supported. If a project needs it, the vendored single file ([ADR 0005](0005-installed-package-plus-a-generated-single-file-copy.md)) is where a backport would go, not the package.
