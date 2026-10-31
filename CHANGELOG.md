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
- Reports a dependency file it *meant* to read and could not — damaged, or not text — as making the whole run incomplete, with the reason, and exits 2. `--only` cannot narrow it away. ([ADR 0009](docs/adr/0009-an-unread-file-makes-the-run-incomplete.md))
- Treats a project where **nothing at all** could be checked, every dependency file being of a kind it has no reader for, as incomplete rather than clean: exit 2, naming the files and `accept_unread`, which is how a project says it is expected. Partial coverage still passes. ([ADR 0010](docs/adr/0010-a-run-that-checked-nothing-is-not-a-pass.md))
- Refuses a misspelt policy kind. `[[policy.ignore_packages]]` used to be read as no policy at all.
- Names each advisory's own smallest fix beside the one version that clears them all, so a package with dozens of advisories says which single upgrade clears which.
- Reads a manifest saved as UTF-8, UTF-16 or UTF-32, by its byte-order mark.
- Follows `-r` and `-c` includes in a requirements file, where the included file is one the walk would not reach on its own.
- Recognises a release tag prefixed with the project's name, such as `jq-1.6`.

**Using it**
- `stocktake`, with `--only`, `--format text|json|sarif|summary`, `--root`, `--config`, `--environment`, `--refresh`, `--all-advisories`.
- A pytest plugin, **off until a project asks for it** with `stocktake = true` or `--stocktake`. It fails, warns and skips by the same rules as the command line, because both go through the same code.
- `stocktake init`, which writes a four-line test file and a commented `.stocktake.toml`, and overwrites nothing.
- `stocktake vendor`, which writes the whole core as one self-contained file for a project that cannot take a dependency. It carries `assert_safe(root)`, one call that raises with the whole report, for a project driving the check from a plain script.
- `STOCKTAKE_OFFLINE=1`, which makes a run answer from its cache and request nothing. Anything not cached is `unknown`, so the run is incomplete rather than clean.
- SARIF 2.1.0 output, validated against the published schema by the test suite, so the findings appear in GitHub's code-scanning view on the lines they came from.
- `--format json` carries `schema_version`, `stocktake_version` and `complete`, so a script can refuse a shape it does not know and can tell "this project is fine" from "this run did not manage to look". `--only` narrows the findings in every format, worst severity first.
- `.stocktake.toml` (or `[tool.stocktake]` in `pyproject.toml`): `ecosystems`, `exclude`, `accept_unread`, `environment`, `cache.ttl_hours`, and the policy. Every value **and every key** is validated as it is read: an unknown ecosystem name and an unknown setting are both refused rather than ignored, and a misspelt key gets a suggestion.
- Policy entries that need a reason and a date, where an entry past its date fails the check until it is decided again. Three kinds: `ignore_advisories` for one advisory, `ignore_package` for a package at a version with every advisory against it, and `hold_back` for being out of date (which never suppresses a vulnerability).
- An accepted vulnerability keeps its own `accepted` status and its own section listing every advisory being carried, counts in the headline, the summary and the JSON, and a SARIF warning. `--only` cannot narrow it away. ([ADR 0011](docs/adr/0011-accepting-a-vulnerable-package.md))

**Keeping it honest**
- Answers cached for six hours, shared across projects. A failed *connection* is retried once; a service that answered is not.
- Only package names and versions leave the machine. Nothing in a project is ever modified, and nothing it finds is ever executed.
- No runtime dependencies at all, enforced by a test.

### Fixed

Three things found by running it against real projects rather than by design, and the rest found by handing it to two projects that had never seen it ([trial reports](docs/feedback/)). Each has a regression test.

- **A declared range is resolved against the project's own environment**, not against whichever interpreter happens to be running StockTake. Before this, `uv tool install stocktake` — the recommended way in — would have reported every project's ranges at the versions in StockTake's own virtual environment. ([ADR 0006](docs/adr/0006-which-environment-an-installed-version-comes-from.md))
- **A tag its publisher advances is a range, not a version.** `uses: actions/checkout@v7` was reported as needing 7.0.1, which is an update that happens by itself. A major gap is still reported. ([ADR 0008](docs/adr/0008-a-tag-its-publisher-moves-is-a-range.md))
- **Advice is tied to the ecosystem it is about.** A project with no Python in it was being told to point StockTake at a Python environment; a Node project whose `node_modules` is missing is now told to run `npm install` instead.
- **A dependency file that could not be read is reported, not skipped.** A truncated `package.json`, a `requirements.txt` saved as UTF-16 and a binary file named `requirements.txt` each produced `nothing found to check` and exit 0. The UTF-16 one is now read properly; the other two make the run incomplete and name the reason. ([ADR 0009](docs/adr/0009-an-unread-file-makes-the-run-incomplete.md))
- **The one-line summary no longer claims more than it checked.** Five unpinned dependencies produced `nothing unsafe, 0 outdated (5 checked)`; they produce `nothing could be checked (0 of 5 checked, 5 unpinned)`.
- **A withdrawn release stays withdrawn when it also has an advisory.** The status takes the more actionable of the two, which meant the headline said `0 withdrawn` about a project that had one.
- **`stocktake vendor deps` writes `deps/stocktake_vendored.py`.** It used to write a Python module into a file called `deps`.
- **A failure says what happened on its first line.** It began with a blank line, so pytest's one-line summary printed `FAILED stocktake_dependency_check - ` and nothing after the dash.
- **The report header uses the local date.** A run at 19:46 on the 30th printed `2026-10-31`, because it was the UTC date.
- **The unreadable-file message is printed once**, not to stdout and stderr both.
- **The CI snippet in the README carries `shell: bash`**, without which `|| [ $? -eq 1 ]` is a parse error on a Windows runner. This repository's own code-scanning workflow had the same problem in the other direction, using the `|| true` the README warns against.
