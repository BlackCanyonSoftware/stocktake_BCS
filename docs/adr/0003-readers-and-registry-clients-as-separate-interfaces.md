# ADR 0003: Readers and registry clients as separate, narrow interfaces

- **Date:** 2026-10-29
- **Status:** accepted

## Context
The user's requirement is a tool that goes into *all* of their projects, "some of which might need to strip from it to fit". The agreed v1 scope covers Python, npm, GitHub Actions and container base images, with Go and Rust later. That is eight-ish ecosystems eventually, each needing two different things: a way to read what a project declares, and a way to ask a registry about it.

The `ai-suite` implementation has both concerns in one 500-line module, with `scan_repo` reaching into Dockerfiles and `pyproject.toml` directly and `Registry` holding PyPI, GitHub and OSV methods side by side. At one ecosystem that is the right size. At eight it becomes the file nobody wants to open, and the risk named in the writeup — the scanner silently missing a pin — gets harder to guard against because there is no seam to test at.

## Options considered

**A. Two narrow interfaces, `Reader` and `Registry`, with one implementation file each per ecosystem.** A reader turns a path and its bytes into `Dep`s and never touches the network. A registry client turns a name into a newest version and advisories and never touches the project. Each gets its own guard test.

**B. One class per ecosystem, doing both.** Fewer files, and "everything about npm is in npm.py" is appealing. But it couples reading to fetching, so a reader can no longer be tested without a fake network, and the natural shape is lost: OSV serves every ecosystem from one batched endpoint, so an `NpmEcosystem` class would either duplicate OSV handling or reach into a shared one anyway.

**C. Keep one module and let it grow.** Honest about where the project is today — one real ecosystem — and YAGNI argues for it. Rejected because the v1 scope is already four ecosystems, so the third occurrence that justifies the abstraction is present at the start, not speculative.

**D. Plugin discovery through entry points from day one,** so readers can live outside this repository. Rejected as speculative: nobody outside this repository wants to write a reader yet. The interface is designed so that this can be added later without changing any reader.

## Decision
Option A.

```python
class Reader(Protocol):
    name: str                                                    # "python", "npm", "workflows", "containers"
    def interested(self, path: Path) -> bool: ...
    def read(self, path: Path, text: str, ctx: Context) -> Iterable[Dep]: ...

class RegistryClient(Protocol):
    ecosystem: str                                               # "PyPI", "npm", "GitHub", "Docker"
    def latest(self, name: str) -> Versions | None: ...          # newest, plus withdrawn versions
```

Advisories stay separate from `RegistryClient`, because OSV answers for every ecosystem from one batched endpoint; it is one client taking `(ecosystem, name, version)` triples, not one per ecosystem.

`Context` carries the project root and an `installed(name)` callable, so a reader can report the version actually present in the environment without importing `importlib.metadata` itself — which is also what makes that behaviour testable with a dict.

Readers and clients are registered in a list in `readers/base.py` and `registries/base.py`. A reader runs only when its ecosystem is enabled for the project ([ADR 0002](0002-one-toml-config-file-at-the-project-root.md)).

Each reader ships with a guard test of the same shape: count what the fixture declares using an independent regular expression, count what the reader found, and fail if they differ. This is the pattern that caught `uv tool install maigret==0.6.6` being invisible in the original, and it is a required part of adding a reader, not an optional extra.

## Consequences
- **Good.** Adding an ecosystem is one file in `readers/`, one in `registries/`, two list entries and a guard test. Nothing existing changes, which is the Open-Closed principle doing actual work here.
- **Good.** Readers are tested with a string and a `tmp_path`, with no network and no fake network. Registry clients are tested with a fake fetch and no filesystem. Both kinds of test stay fast and obvious.
- **Good.** A project that enables only `python` never loads or runs the npm reader, which is the "strip it down to fit" requirement met by configuration rather than by deleting code.
- **Cost.** More files than the problem strictly has today, and two indirections to follow when reading the code. Judged worth it at four ecosystems in v1.
- **Cost.** Two registries of implementations to keep in step with the files beside them. A test asserts that every module in `readers/` is registered, so a reader cannot be added and silently never run.
- **Cost.** The `Dep` shape has to suit every ecosystem. It already nearly does; `role` grows the values `runtime` and `ci` alongside `image` and `dev`.
