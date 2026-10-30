# ADR 0005: An installed package, plus a generated single-file copy

- **Date:** 2026-10-29
- **Status:** accepted

## Context
The requirement is that StockTake is "easy to add alongside any existing test suites", in every project the author maintains, "some of which might need to strip from it to fit". Those projects differ in what they will tolerate: a Python service with a `pyproject.toml` can take a dev dependency without a second thought, while a Dockerfile-only repository or a Node project has nowhere natural to declare a Python dependency, and a locked-down project may not be allowed a new one at all.

The writeup proposed both "a pytest helper so any project adds one test" and "one copy-in test file", without choosing.

## Options considered

**A. Installed package only.** `uv tool install stocktake` or a dev dependency, plus a pytest plugin. One code path, fixes propagate by upgrading. Projects that cannot add the dependency are simply not served.

**B. Copy-in single file only.** Drop one file in, no install, no dependency, works anywhere Python 3.11 runs. Zero friction per project — and every project drifts to its own private copy, so a fix made here reaches nothing.

**C. Both, with the single file generated from the package and guarded by tests.** The package is the only source of truth. The copy is a build artefact of it, produced by `stocktake vendor`, and two tests prove the copy is current and behaves identically.

**D. Both, with the single file maintained by hand.** Two implementations to keep in step. Rejected immediately: this is the arrangement that guarantees the copy is subtly wrong.

## Decision
Option C.

**The primary path** is the installed package: `uv tool install stocktake` for the command line, or `stocktake` in a dev dependency group plus the pytest plugin, registered as a `pytest11` entry point. A project adds the check by enabling the plugin, or by running `stocktake init` to write a small `tests/test_dependencies.py` it then owns. Either way, no change to how the suite is run (US-010).

**The fallback** is `stocktake vendor <path>`, which writes a single self-contained `.py` file. It is generated, not written: the core modules are concatenated in dependency order with intra-package imports stripped. Two guard tests keep it trustworthy:

1. **It is current.** Regenerating from the current source must reproduce the committed copy byte for byte, so a change to the core that is not reflected in the vendored file fails CI.
2. **It behaves the same.** The core behavioural test suite is parameterised over both the package and the vendored module, so the copy is not merely present but correct.

The vendored file bundles every reader and has no configuration discovery beyond `.stocktake.toml`; those limitations are documented where the command is.

This is M4 work. M0 ships the package alone, because a vendoring step for code whose shape is still settling is wasted effort.

## Amendment, 2026-10-30 (built in M4)
Two things turned out differently in the building, both recorded here rather than left to be discovered:

**The equivalence guard is a focused test, not the whole suite run twice.** This record promised that "the core behavioural test suite is parameterised over both the package and the vendored module". That is not what shipped. The copy is one flat module, so `from stocktake.readers.npm import parse_npm_spec` cannot resolve against it; making the existing suite run against the copy would mean registering synthetic submodule entries in `sys.modules` and then excluding the handful of tests that inspect `__module__` or read the package's files from disk. A guard that needs a list of exceptions is a guard nobody trusts.

What shipped instead compares the two on what actually matters: both are run against one fixture project exercising five readers — a Dockerfile, a `pyproject.toml`, a `requirements-dev.txt`, a `package.json`, a workflow, and an unread `go.mod` — through the same fake network, and the **text, JSON and SARIF reports must be identical**. A second test asserts that fixture really does produce vulnerable, outdated, unpinned and current findings across three ecosystems, so the comparison cannot pass by saying nothing. That is a narrower claim than "every test runs twice" and a much stronger one than the alternative, which was a guard with a footnote.

**The generator refuses rather than emitting, in four cases**, which is where most of its value turned out to be: two modules defining the same top-level name (in one flat file the second wins silently, giving wrong answers rather than crashes), a module importing something deliberately left out, an import cycle, and nothing to copy. The third of those caught a real bug immediately — `cli.py` imports `init_project.py`, which is not in the copy, so the command line had to be excluded too. Dependency order is computed from the imports rather than listed, so the generator cannot fall behind the package.

The byte-for-byte guard also earns its keep straight away: a `ruff format` pass touched one core module and the committed copy went stale within the same session. The test caught it.

## Consequences
- **Good.** Every project the author has can take the check, including the ones that cannot take a dependency.
- **Good.** One source of truth. A vendored copy that has gone stale fails a test here rather than drifting unnoticed in someone else's repository.
- **Good.** The generator forces a discipline that is good for the code anyway: the core modules must have a clean dependency order and no cycles, or concatenation does not work.
- **Cost.** A code generator, and the `# stocktake:vendor-skip` style markers it needs around imports. Perhaps 80 lines plus its tests.
- **Cost.** Running the behavioural suite twice makes the test run slower. Negligible — the core tests are offline and fast by design.
- **Cost.** A vendored copy in another repository still has to be refreshed deliberately by re-running `vendor`. There is no mechanism that tells a project its copy is old; the check it performs is still correct, just missing newer readers and fixes. Accepted, and stated in the docs.
- **Cost.** Two documented ways in, which is one more than ideal for a new reader of the README. Handled by presenting the installed package as *the* way and the vendored file as the escape hatch, not as an equal option.
