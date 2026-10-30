# ADR 0006: Which environment an installed version comes from

- **Date:** 2026-10-30
- **Status:** accepted

## Context
A manifest that declares a range — `pyproject.toml`'s `flask>=2`, a `Pipfile`'s `"*"`, a `requirements.txt` line with no `==` — says nothing about what is actually running. So StockTake resolves those against the version *installed*, and checks that.

Milestone 0 inherited the original's implementation of this: `importlib.metadata.version(name)`, asking whichever interpreter happens to be running StockTake. In the `ai-suite` repository that was correct, because the tool lived inside the project and ran from the project's own virtual environment. As a standalone tool it is wrong, and verification during Milestone 1 showed exactly how wrong:

- A demo project with no environment of its own reported `ruff` at **0.17.3** — the version in *StockTake's* virtual environment. The demo project had never installed ruff at all.
- The recommended installation, `uv tool install stocktake`, puts StockTake in its own isolated environment. Under the inherited behaviour, *every* project checked that way would have had its ranges resolved against StockTake's own dependencies.
- `stocktake --root ../other-project` resolved that project's ranges against this one's environment.

Each of those is a wrong version reported on a security check. A wrong version means a wrong advisory lookup, in either direction: a vulnerability missed, or one reported that the project does not have. That is the single thing NFR-7 says must not happen.

## Options considered

**A. Resolve against the project's own environment, in a documented order, and claim nothing when none can be found.** Look for the project's `.venv` or `venv`, the environment active in the shell when it is this very project being checked, and the running interpreter when it genuinely is the project's environment. Otherwise report the dependency as unpinned and say why, with a flag to name an environment explicitly.

**B. Keep asking the running interpreter.** No work, and correct in the one case where StockTake is installed as a dev dependency of the project it is checking. Silently wrong in every other case, including the recommended one. Rejected: a dependency checker that reports the wrong version is worse than one that reports nothing.

**C. Stop resolving ranges altogether.** Report every range as unpinned and check only what is literally pinned. Honest, simple, and throws away a genuinely useful feature — the `ai-suite` run that started this whole project found most of its advisories against *installed* dev dependencies, not against pins.

**D. Run the project's own interpreter as a subprocess** (`<project>/.venv/bin/python -m pip list --format=json`) and read what it says. Authoritative, and the only way to be certain. Rejected: executing a binary found inside a scanned directory is exactly what a read-only tool must not do, and it would make the check slow and platform-fragile.

## Decision
Option A. One function, `find_environment(root, environment=None)`, resolves in this order and records which answer it used:

1. **An environment named by the caller** — `--environment PATH`, or `environment = "..."` in the project's config (relative to the project root). If that path holds no environment, the run stops with exit 2 rather than falling back: the user asked for something specific.
2. **The project's own `.venv` or `venv`.**
3. **The environment active in this shell**, but only when the project being checked is the current directory — otherwise an activated environment would leak into a `--root` check of somewhere else.
4. **The interpreter running StockTake**, but only when its prefix is inside the project root, which is the "installed as a dev dependency" case.
5. **Nothing.** Dependencies declared as a range are reported as unpinned, and the report carries a note saying no environment was found and how to name one.

Versions are read from the `*.dist-info` directory names in `site-packages`, which carry both the name and the version without a single file being opened and without anything being executed.

An environment that exists but is empty is a real answer (`{}`), distinct from no environment at all (`None`). Conflating them would have made an empty virtual environment fall through to the next candidate.

## Consequences
- **Good.** The recommended installation path now reports correct versions, which it did not before.
- **Good.** `--root` is trustworthy: checking another project no longer resolves its ranges against this one's environment.
- **Good.** Nothing is executed and no file is opened to do it, so the read-only promise (NFR-3) is untouched.
- **Good.** The failure is now visible and actionable. The note names the flag, instead of the report quietly containing versions from the wrong place.
- **Cost.** A project whose environment lives somewhere unguessable — installed globally, conda, virtualenvwrapper, a container — gets nothing resolved until someone passes `--environment` once. The brand-kit project among the author's repositories is exactly this case; pointed at the right interpreter it immediately reported 58 advisories against its installed Pillow, and without that flag it reported nothing at all.
- **Cost.** Reading `dist-info` directory names trusts the filename rather than the metadata inside. A hand-mangled directory name would be misread. Acceptable: it is the documented layout, it is what makes this free, and the alternative is opening thousands of files.
- **Cost.** More resolution rules than one would like, each needing its own test. They are in one function with one docstring, and the report says which rule answered.
