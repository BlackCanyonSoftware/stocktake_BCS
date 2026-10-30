# ADR 0007: The pytest plugin is opt-in

- **Date:** 2026-10-30
- **Status:** accepted

## Context
The point of Milestone 2 is that any project can adopt the check in one step. The obvious way to do that in Python is a `pytest11` entry point: pytest discovers plugins through it automatically, so simply installing the package would make the dependency check part of the project's suite with no configuration at all. Zero steps, not one.

That is also the problem. An entry point makes the plugin load in **every** pytest run in **every** environment where StockTake happens to be installed — including environments where it was pulled in as a transitive dependency of something else, and including runs of test suites whose owners have never heard of it. If the check ran by default, installing a package would:

- add a test that makes network requests to three public services, in suites that may deliberately run with no network;
- fail builds for a dependency problem the project did not ask to be told about, on somebody else's schedule;
- do both to a project whose maintainer has no idea where the new test came from.

A dependency that behaves that way is a bad guest, and the first thing anyone would do about it is uninstall. That is the same failure mode [ADR 0004](0004-only-unsafe-findings-fail-the-build.md) is built to avoid, arriving from a different direction: the tool has to be something people leave switched on, and nothing gets switched off faster than something that switched itself on.

## Options considered

**A. Entry point registers the plugin; the check runs only when the project asks.** `stocktake = true` in the project's pytest configuration, or `--stocktake` for a single run. One line, in the file where a project already configures pytest.

**B. Entry point, and the check runs by default.** Zero configuration, and every one of the problems above.

**C. No entry point at all; the project adds `pytest_plugins = ["stocktake.pytest_plugin"]` to its root `conftest.py`.** Also explicit, and no risk of loading where it is not wanted. But it has to go in the *root* conftest specifically, which is a pytest rule people get wrong, and a project with no conftest has to grow one. More than one step, and the error when it goes in the wrong place is obscure.

**D. No plugin; `stocktake init` writes a test file and that is the only way in.** Honest and simple, and the written file is readable, which is a real virtue. But it is a file the project then owns and has to maintain, and it cannot pick up improvements to the rules without being rewritten.

## Decision
Option A, with option D kept alongside it as the path for projects that would rather own the file.

```toml
[tool.pytest.ini_options]
stocktake = true
```

- `--stocktake` switches it on for one run without editing anything; `--no-stocktake` switches it off for one run without editing anything (useful on a plane, or in a job that must not touch the network).
- The check is added as one item at the end of the session, carrying a registered `stocktake` marker, so `-m "not stocktake"` and `-k` work on it like any other test. The hook runs `tryfirst` precisely so that pytest's own selection still applies to it.
- Its node id is set explicitly to `stocktake_dependency_check`. Parented on the session, the default would have been `::stocktake_dependency_check`, with an empty path in front of it in every verbose line and every JUnit report.
- `stocktake init` writes a four-line test file for the other path. Both paths call `assert_dependencies_are_safe`, and both get their rules from `stocktake.check`, so they cannot drift from each other or from the command line.
- **StockTake switches it on for itself.** `stocktake = true` is in this repository's own `pyproject.toml`, and the hand-written live check it replaced has been deleted. Its own suite is the plugin's first consumer, so a plugin that stops working breaks this suite before it reaches anybody else's.

## Consequences
- **Good.** Installing StockTake, deliberately or transitively, changes nothing about anybody's test run until they ask.
- **Good.** Adoption really is one line, in a file the project already has, and it needs no new file and no conftest.
- **Good.** The off switch works per run, which matters for the offline case — and that case is a skip rather than a failure anyway ([ADR 0004](0004-only-unsafe-findings-fail-the-build.md)).
- **Good.** Dogfooding means the plugin cannot rot unnoticed. A guard test asserts the arrangement is still in place, so it cannot be quietly switched off either.
- **Cost.** Two ways in to document, which is one more than ideal. Handled by presenting the plugin as *the* way and `stocktake init` as the alternative for projects that want the file, not as an equal choice.
- **Cost.** A project that runs `init` *and* switches the plugin on checks itself twice. Harmless — the second run is served entirely from the six-hour cache — but worth knowing, and there is a test that records it.
- **Cost.** Injecting a synthetic item is slightly unusual for a pytest plugin, and relies on `from_parent(session, ...)` continuing to work. Mitigated by testing it through `pytester`, which runs a real pytest in a scratch project and asserts on what a suite actually sees rather than on the plugin's internals.
- **Accepted limitation.** The item has no file of its own, so its reported location is the project root. There is nowhere more honest to point: the check is about the project, not about any one file in it.
