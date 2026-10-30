# ADR 0002: One TOML config file at the project root

- **Date:** 2026-10-29
- **Status:** accepted

## Context
The `ai-suite` implementation keeps its decisions in `config/deps-policy.yaml` and its exclusions in a hard-coded `EXCLUDED` tuple in the source, which lists paths that only exist in that one repository (`docker/dev/osint`, `tests/study`). Neither survives being made into a general tool: the exclusions have to move into the project, and the policy file costs a PyYAML dependency that [ADR 0001](0001-python-with-a-standard-library-only-core.md) will not pay.

There are also more things to configure than policy: which ecosystems to read, what to exclude, how long to cache, and which unread manifests have been acknowledged.

## Options considered

**A. One `.stocktake.toml` at the project root, holding everything.** TOML parses with `tomllib` from the standard library. One file to find, one file to document, one file to put in version control and review in a pull request.

**B. Keep YAML.** The existing file and its comments carry over unchanged, and YAML's inline `{id: ..., reason: ..., until: 2026-12-01}` form is pleasant for policy entries. Costs PyYAML, which contradicts ADR 0001, and `yaml.safe_load` happily turns an unquoted date into a `date` and an unquoted `no` into `False`, which has to be defended against.

**C. A `[tool.stocktake]` table inside `pyproject.toml`.** Idiomatic for Python tooling and means no extra file. But StockTake is meant to check Node projects and bare Dockerfile repositories too, which have no `pyproject.toml`, and policy entries churn far more than the rest of a `pyproject.toml` ought to.

**D. Two files: settings and policy.** Separates the rarely-changed from the frequently-changed, which is a real distinction. Rejected as two things to find and explain for a tool whose whole configuration fits on one screen.

## Decision
Option A, with `pyproject.toml`'s `[tool.stocktake]` accepted as a fallback for Python projects that prefer it. `.stocktake.toml` wins if both exist, and the tool says so rather than silently merging.

```toml
# .stocktake.toml
ecosystems = ["python", "binaries"]         # which readers to run; default: all of them
exclude = ["vendor", "tests/fixtures"]      # added to the built-in defaults, never replacing them
accept_unread = ["go.mod"]                  # manifests this project knows cannot be read yet
environment = "tools/env"                   # where its Python environment is, if not ./.venv (ADR 0006)

[cache]
ttl_hours = 6

[[policy.ignore_advisories]]
id = "GHSA-xxxx-xxxx-xxxx"
reason = "only reachable through a feature we do not use"
until = 2026-12-01

[[policy.hold_back]]
package = "pillow"
reason = "12.4 changes the PNG writer; rebuild the logo samples first"
until = 2026-12-01
```

`until` is a native TOML date, which `tomllib` returns as a `datetime.date`, so there is nothing to parse and no ambiguity about format. A string is still accepted and parsed as ISO, because people will write one.

A note on one key's name: `ecosystems` lists **reader groups** (`python`, `binaries`, later `npm` and `workflows`), which are not the same strings as a finding's `ecosystem` field (`PyPI`, `GitHub`). A group can cover more than one registry — the Python group reads Dockerfile pins, manifests and lock files, all of which are PyPI. `ecosystems` is kept as the key anyway because it is the word someone reaches for when writing the file, and because it is what the PRD promised; `Reader.group` is the name in the code, and `ARCHITECTURE.md` explains the relationship in one line.

Every value is validated as it is read, and an unknown ecosystem name is refused rather than ignored — a typo that silently switched half the check off would be the worst kind of failure for a file like this.

The policy semantics are unchanged from the original and are not up for renegotiation here: every entry needs a `reason` and an `until`, an entry missing either is a failure, and an entry past its date is a failure. See [ADR 0004](0004-only-unsafe-findings-fail-the-build.md).

## Consequences
- **Good.** No runtime dependency for configuration, and `until` dates are typed by the format rather than by us.
- **Good.** The hard-coded exclusion list disappears, which is what makes the tool general (US-040, US-041).
- **Good.** A project that enables only the ecosystems it has makes no requests for the ones it does not, which is both faster and less noisy.
- **Cost.** TOML's `[[array.of.tables]]` form is more verbose than YAML's inline maps: four lines per policy entry instead of one. Mitigated by `stocktake init` writing a commented starter file, and the verbosity arguably suits an entry that is a deliberate decision with a justification.
- **Cost.** Migrating the existing `ai-suite` policy file is manual. It is three entries; it will be done when that repo is switched over, which is deliberately not part of this project.
- **Cost.** Two possible locations for configuration. Kept honest by `.stocktake.toml` always winning and the tool naming which file it used.
