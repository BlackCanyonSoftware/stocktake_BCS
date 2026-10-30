# Changelog

What changed, for people using StockTake. The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

Everything below is unreleased: StockTake has not been published anywhere yet, and `0.1.0` is what the package metadata says while that is still true. The first entry under a version number will be the first release.

### Added

**The check itself**
- Reads Python dependencies from Dockerfile `pip`/`uv`/`pipx` installs, `pyproject.toml`, `Pipfile`, `requirements*.txt`, `constraints*.txt`, and `uv.lock`, `pdm.lock`, `poetry.lock` and `Pipfile.lock`.
- Reads npm dependencies from `package.json` and `package-lock.json` (both layouts), resolving declared ranges against `node_modules`, including dependencies hoisted to the top of a workspace.
- Reads GitHub Actions pins from `.github/workflows/*.yml` and `action.yml`, taking the version from the conventional `# v4.1.1` comment when the ref is a commit SHA.
- Reads GitHub release downloads in Dockerfiles, resolving `${VERSION}` against the nearest earlier assignment.
- Asks PyPI, the npm registry and the GitHub releases API for the newest version, and [OSV](https://osv.dev) for advisories against the exact version in use.
- Fails only on a vulnerable release, a withdrawn release, or a policy entry past its date. A newer release warns. Registries that cannot be reached make the check *incomplete*, never clean.
- Merges advisories that are the same problem reported twice, ranks them worst first, and names the single version that clears them all.
- Reports a dependency manifest of a kind it cannot read yet, rather than passing over it in silence.

**Using it**
- `stocktake`, with `--only`, `--format text|json|sarif|summary`, `--root`, `--config`, `--environment`, `--refresh`, `--all-advisories`.
- A pytest plugin, **off until a project asks for it** with `stocktake = true` or `--stocktake`. It fails, warns and skips by the same rules as the command line, because both go through the same code.
- `stocktake init`, which writes a four-line test file and a commented `.stocktake.toml`, and overwrites nothing.
- `stocktake vendor`, which writes the whole core as one self-contained file for a project that cannot take a dependency.
- SARIF 2.1.0 output, validated against the published schema by the test suite, so the findings appear in GitHub's code-scanning view on the lines they came from.
- `.stocktake.toml` (or `[tool.stocktake]` in `pyproject.toml`): `ecosystems`, `exclude`, `accept_unread`, `environment`, `cache.ttl_hours`, and the policy. Every value is validated as it is read, and an unknown ecosystem name is refused rather than ignored.
- Policy entries that need a reason and a date, where an entry past its date fails the check until it is decided again.

**Keeping it honest**
- Answers cached for six hours, shared across projects. A failed *connection* is retried once; a service that answered is not.
- Only package names and versions leave the machine. Nothing in a project is ever modified, and nothing it finds is ever executed.
- No runtime dependencies at all, enforced by a test.

### Fixed

Three things found by running it against real projects rather than by design. Each has a regression test.

- **A declared range is resolved against the project's own environment**, not against whichever interpreter happens to be running StockTake. Before this, `uv tool install stocktake` — the recommended way in — would have reported every project's ranges at the versions in StockTake's own virtual environment. ([ADR 0006](docs/adr/0006-which-environment-an-installed-version-comes-from.md))
- **A tag its publisher advances is a range, not a version.** `uses: actions/checkout@v7` was reported as needing 7.0.1, which is an update that happens by itself. A major gap is still reported. ([ADR 0008](docs/adr/0008-a-tag-its-publisher-moves-is-a-range.md))
- **Advice is tied to the ecosystem it is about.** A project with no Python in it was being told to point StockTake at a Python environment; a Node project whose `node_modules` is missing is now told to run `npm install` instead.
