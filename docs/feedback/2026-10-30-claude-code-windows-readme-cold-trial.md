# StockTake test report: Claude Code session (README-first, all five routes), 2026-10-30

- Source: Claude Code session (Black Canyon Software, Pixel Galaxy Studio project), model Sonnet 5.5, asked to try StockTake as a stranger and write this report
- Date: 2026-10-30 (local, UTC-7; StockTake's own report header says 2026-10-31, see 8.9)
- StockTake version / commit tested: `079275e` (`git rev-parse --short HEAD`), installed with `pip install git+https://github.com/BlackCanyonSoftware/stocktake_BCS`, tool prints `stocktake 0.1.0`
- Platforms: Windows 10 Pro; CLI, plugin and `init` on Python 3.13.3; the vendored file on Python 3.11.9 with nothing installed; npm 11.20.0. No Linux, no macOS, no GitHub Actions runner.
- Ecosystems exercised: python (requirements.txt, pyproject.toml), npm (package.json, package-lock.json, an installed `node_modules`), workflows (`uses:` pins), unread manifests (go.mod, pnpm-lock.yaml). Not exercised: binaries, Pipfile, poetry/uv/pdm locks, Dockerfile pins, SHA-pinned actions.
- Verdict: Every route in the README that can be run from a shell works as written and every finding I could check was right (exact agreement with OSV and with `npm audit` on three projects), but the CI snippet does not parse on a Windows runner, the vendored-file snippet fails with a bare `AssertionError` that shows nothing, and a project whose every manifest is unread still exits 0.

---

## 1 Summary

**Good**

- Install from git, `stocktake = true`, `stocktake init`, `stocktake vendor` and the exit-code idiom all behaved as the README says, on the first attempt, without reading anything but the README.
- Zero false positives in anything I ran. On `lodash 4.17.15` it found 6 advisories, and a direct OSV query returns the same 6 ids. On two real Node projects the set of vulnerable packages equals `npm audit`'s set, name for name, and the per-package advisory counts match (electron 46, tar 12, extract-zip 2).
- The failure-mode design is right where I pushed on it: a truncated `package.json` exits 2 and says so; a dead network exits 2; an unknown config key is refused with a suggestion; a UTF-16 `requirements.txt` is read; an expired policy entry fails.
- Fast. A warm run is 1.7 s on a 2-dependency project; a cold 433-dependency npm project took 12.9 s.

**Bad**

- The README's CI step (`... || [ $? -eq 1 ]`) is a parse error in PowerShell, 5.1 and 7, which is the default shell on `windows-latest`. StockTake's own CI matrix includes Windows. The README does not say to set `shell: bash`. Verified. (9.3, P1)
- The vendored-file snippet ends `assert stocktake.failure_text(report) is None`. When that fails the output is a traceback ending in a bare `AssertionError`: none of the report, the finding or the advisory is shown. The snippet is the whole instruction for route 3. Verified. (9.2, P1)
- A project whose manifests are all of a kind with no reader (a Go project: `go.mod` and `pnpm-lock.yaml`) reports `0 checked`, lists both files as UNREAD, and exits **0**. The README's definition of exit 0 is "nothing unsafe, and the whole project was checked", which is false here. (6.3, P1)

**Surprising**

- `STOCKTAKE_OFFLINE=1` has no effect on the command line. With an empty cache it still queried all four services and exited 1. It works in the pytest plugin, which is where the README lists it. (8.8)
- `hold_back` does not suppress a vulnerable finding (correct per the README's table, and I confirmed it), so the only way to accept a known advisory is one `ignore_advisories` entry per advisory id. That is 58 entries for the electron and tar findings of the project in section 11. (11)

## 2 Method

- Read order: `docs/feedback/README.md` and `docs/HANDOFF.md` first, because the owner pointed me at them, then the root `README.md` in full. I did **not** read `docs/PRD.md`, `ARCHITECTURE.md`, the ADRs, `ROADMAP.md`, or the body of the earlier trial report; I opened that report only far enough to copy its header and heading style. `AGENTS.md` was loaded into my context automatically. So this is not a fully cold read: HANDOFF.md told me, before I began, which four routes had never been tried by an outsider and what the earlier trial found. I treated the README, not HANDOFF.md, as the authority on how to use the tool.
- A checkout of the repository was on disk, but I did not use it. I made a fresh `py -3.13 -m venv` outside the repository and installed with the README's own `pip install git+https://github.com/BlackCanyonSoftware/stocktake_BCS`. The `git clone` + `pip install -e .` route at the top of the Install section was **not** exercised.
- Ground truth was written into the scratch-project builder before the first run (`EXPECTED.md` beside each project in `examples/w01` to `w04`). Cross-checks: a direct `POST https://api.osv.dev/v1/query`, and `npm audit` (`--package-lock-only` for clones with no `node_modules`).
- Real projects, all read-only: `DayandNight_BCS` (a local checkout, with `node_modules`), and a shallow clone of the Pixel Galaxy Studio branch `main-24h1wy` into a scratch folder (lock file only, no `node_modules`). Nothing in either was changed.
- Not done: a real GitHub Actions run (that needs a push to a repository, which I did not do). I ran the step's shell line locally under `sh` and under PowerShell instead.

## 3 Install and first run (friction log)

| Step | What I did | Result |
|---|---|---|
| 1 | `py -3.13 -m venv env`, then `pip install git+https://github.com/BlackCanyonSoftware/stocktake_BCS` | Built and installed `stocktake-0.1.0` in one command. No dependencies pulled. |
| 2 | `stocktake --version`, `--help` | `stocktake 0.1.0`. The help text is good: it carries the exit codes, the `|| true` warning and the privacy statement. |
| 3 | `stocktake --root <project>` on a project with nothing to find | Clear, exit 0. |
| 4 | Same on a project with a vulnerable pin | Exit 1, readable, worst advisories first, the fix version named. |

Friction, in the order I met it:

1. The first block under "Install" is `git clone` + `py -3.11 -m venv` + `pip install -e .`. That is the contributor route. The route an outsider wants (`pip install git+...`) is the *second* block, below the paragraph about Python versions. I took the second because the note above both said it works; a reader who copies the first block gets a development install of a tool they only wanted to run.
2. The first block hard-codes `py -3.11` while the paragraph under it says any 3.11+ will do. On a machine with only 3.13 the first block fails at line 2.
3. The route table says routes 1 and 2 need StockTake "as a dev dependency", but today the only way to install it is from git, and no line anywhere shows how to declare *that* as a dev dependency (`stocktake @ git+https://...` in a requirements file, or `uv add --dev git+...`). The commented lines show the PyPI form that does not work yet. I installed it directly into the project's venv instead and did not test the dev-dependency forms (`uv` is not installed here).
4. Date in the headline: see 8.9.

## 4 Results per feature/command

| Route / command | Result |
|---|---|
| 5 Just look: `stocktake --root PATH` | Works; changes nothing in the project (checked with `git status`). |
| 1 pytest, `stocktake = true` in `[tool.pytest.ini_options]` | Baseline `1 passed`; after the line `1 failed, 1 passed`, exit 1, the full report printed in the failure; `FAILED stocktake_dependency_check -` (nothing after the dash). |
| 1, `pytest.ini` and `tox.ini` with `[pytest]` | Both ran the check: `2 passed, 1 warning`. |
| 1, `setup.cfg` with `[tool:pytest]` | Ran the check: `2 passed, 1 warning`. |
| 1, `setup.cfg` with `[pytest]` | pytest itself refuses: `Failed: [pytest] section in setup.cfg files is no longer supported, change to [tool:pytest] instead.` The README's claim is accurate. |
| 1, `--no-stocktake`, `-m "not stocktake"`, `STOCKTAKE_OFFLINE=1` | All three work: `1 passed`; `1 passed, 1 deselected`; `1 passed, 1 skipped`. |
| 1, `stocktake = true` with StockTake **not installed** in that venv | `1 passed, 1 warning`; the one warning is `PytestConfigWarning: Unknown config option: stocktake`. The README warns this "silently does nothing"; the actual symptom is that one warning, which the README never names. |
| 2 `stocktake init` | Wrote `tests/test_dependencies.py` and `.stocktake.toml`; second run said `left alone; --force overwrites` for both, exit 0. The generated test passed (`2 passed, 1 warning`) and named `click 8.1.7->8.5.0` as the warning. It needs StockTake importable in the project's test environment, which is the "dev dependency" requirement above. |
| 3 `stocktake vendor .` | Wrote one 3069-line `stocktake_vendored.py`. The README snippet, saved as `check_deps.py` beside it, ran on Python 3.11 with nothing installed and passed on a clean project (printed `WARN: 1 dependencies have a newer release...`). On a vulnerable project it fails; see 9.2. |
| 4 CI step | Not run on GitHub. Shell line under `sh`: findings gave step exit 0 and a valid SARIF 2.1.0 with 3 results; a truncated `package.json` gave step exit 1 (the step correctly fails). Under PowerShell it does not parse; see 9.3. |
| `--format summary`, `json`, `sarif` | All three worked; JSON has `schema_version`, `complete`, `unreadable` as documented. |
| `--only outdated` / `vulnerable`, `--all-advisories` | Work; `--all-advisories` on the 52-advisory pillow made the report 62 lines. |
| `[tool.stocktake]` in `pyproject.toml` | Worked (`exclude = ["requirements.txt"]` removed the only file; result `0 checked`, exit 0, see 6.3). |
| `python -m stocktake` | Works. |

## 5 Accuracy

No false positives and no misses in anything I could check.

- `lodash 4.17.15` (npm): StockTake 6 advisories, OSV direct query 6, same ids except that I compared counts and the first five ids by eye, not all six programmatically.
- `DayandNight_BCS` (392 packages, with `node_modules`): StockTake `7 vulnerable (392 checked)`. `npm audit` lists three packages with their own advisories (electron, fast-uri, minimatch); StockTake's seven findings are those same three packages (minimatch at four versions, plus a package.json and lock-file pair). Set difference in both directions: empty. This differs from the three vulnerable packages recorded in HANDOFF.md; the minimatch advisory is new since then, which is how it should behave.
- Pixel Galaxy Studio branch `main-24h1wy` (lock file only): StockTake `11 vulnerable (426 of 433 checked, 7 unpinned)`. `npm audit --package-lock-only` names eight packages with their own advisories: app-builder-lib, builder-util-runtime, electron, extract-zip, glob, ip-address, minimatch, tar. StockTake's eleven findings are those eight packages (minimatch four times). Set difference in both directions: empty. Counts per package match (electron 46, tar 12, extract-zip 2, the rest 1). `npm audit` total is 34 because it also counts packages affected only through another, as the README says.
- `pillow 9.0.0` 52 advisories and `requests 2.19.1` 5 advisories are the figures HANDOFF.md says the earlier work found. I did not verify them independently.
- `actions/checkout@v2` reported as `2 -> 7.0.1 (major)`; `7.0.1` exists.
- The action tags in the README's CI snippet exist: `actions/setup-python` has `v7` and `github/codeql-action` has `v4`, both as the README says (`gh api .../tags`).

## 6 Output formats and exit codes

1. Exit 0 / 1 / 2 as documented in every case I forced: clean → 0, vulnerable → 1, truncated JSON → 2, dead network → 2, unknown config key → 2, malformed TOML → 2, nonexistent `--root` → 2.
2. SARIF: valid-looking 2.1.0 (`version`, one run, `executionSuccessful: True`), `location` is the lock file, which is where the finding lives.
3. **Nothing readable, exit 0.** `w04-only-unread-manifests` (a `go.mod` and a `pnpm-lock.yaml`) prints `0 checked`, a paragraph "Nothing could be checked: every dependency file found is of a kind StockTake has no reader for yet", lists both files under UNREAD, and exits **0**. An empty directory and an `exclude` that removes the only file do the same. The text is honest; the exit code is not, against the README's own definition of 0. For a CI gate on a Go or pnpm project this is a permanently green step that has checked nothing. The README's own rationale for exit 2 ("nothing is claimed either way") applies unchanged.
4. On exit 2 for an unreadable file, the same message is printed **twice**: once as a `stocktake:` notice on stderr and again as the UNREADABLE section of the report. With `2>&1` it reads as a duplicate. (P2)

## 7 Performance and resource use

| Run | Time |
|---|---|
| 2-dependency Python project, cold cache | 15.2 s |
| Same, warm | 1.7 s |
| Same, `--refresh` | 14.3 s |
| 3 npm/workflow findings, cold | 2.2 s |
| 392-package project, cache partly warm | 2.2 s |
| 433-package project, cold | 12.9 s |

The 15 s for two Python packages is almost all the 52-advisory pillow lookup, not the dependency count. Memory and cache size not measured.

## 8 Error handling and edge cases

1. Truncated `package.json` → exit 2, names the file and `Expecting value: line 2 column 1 (char 38)`. Good.
2. Nonexistent `--root` → `... is not a directory`, exit 2.
3. Empty directory → `Nothing was found to check...`, exit 0 (see 6.3).
4. Unknown config key → `unknown setting: `excludes`; did you mean `exclude`?. Valid: ...` exit 2. Useful message; it has a stray `.` after the question mark.
5. Malformed TOML → `is not valid TOML (Invalid value (at end of document))`, exit 2, no line number.
6. UTF-16 `requirements.txt` → read correctly (`1 checked, 1 outdated`).
7. Network unreachable (`HTTPS_PROXY` pointed at a closed port) → `could not check (offline: <urlopen error [WinError 10061] ...>)`, exit 2. The proxy variable is honoured.
8. `STOCKTAKE_OFFLINE=1` on the command line, empty cache: ran the full check, exit 1. Documented only in the pytest table, and `stocktake --help` does not mention it. Either honour it in the CLI (exit 2 with a clear "offline by request"), or say in the table that it is a plugin switch.
9. The report header shows `2026-10-31` when it was 19:46 on 2026-10-30 here (UTC-7). It is the UTC date. Harmless, but it looks like a bug the first time.
10. Expired `hold_back` entry (`until = 2026-01-01`) → a POLICY line in the report and exit 1, as documented. A *live* `hold_back` on a vulnerable package did not hide it (`2 vulnerable`, exit 1), matching the README's "outdated on purpose". `ignore_advisories` with one id removed exactly that advisory from the list and left the package vulnerable.
11. `stocktake = true` without the plugin installed: one `PytestConfigWarning`, tests pass (section 4).
12. `FAILED stocktake_dependency_check - ` ends with a dash and nothing after it, where pytest prints the assertion message after a dash.

## 9 Documentation review (README claims, one by one)

1. **"`pip install git+...` ... verified to give the complete tool"**. True here. The plugin, `init`, `vendor`, SARIF and all four readers were present.
2. **Route 3 snippet, `assert stocktake.failure_text(report) is None`**: runs, and passes on a clean project, but on a failing one the output ends in
   ```
   AssertionError
   ```
   with the traceback pointing at that line. `failure_text` is not in the output, so the person whose build just went red sees no package, no advisory, no hint. Fix: `assert (text := stocktake.failure_text(report)) is None, text` or `msg = ...; assert msg is None, msg`. The plugin route does print the full report on failure (section 4). The generated `init` test calls `assert_dependencies_are_safe(...)`, which I saw pass but did not see fail; the vendored route has no equivalent helper that I could find.
3. **Route 4, `stocktake --format sarif > stocktake.sarif || [ $? -eq 1 ]`**: correct under bash. Under PowerShell 5.1: `The token '||' is not a valid statement separator in this version.` Under PowerShell 7: `ParserError: Missing type name after '['`. GitHub's `windows-latest` defaults to PowerShell. The README's own CI runs Windows and Ubuntu. Add `shell: bash` to the step, or say "Linux/macOS runners, or `shell: bash`". Verified locally in both shells; not verified on a real runner.
4. **"`stocktake = true` ... A Node project, or a Django project using `manage.py test`, needs route 3 or 4. Getting this wrong produces a config line that silently does nothing."** Accurate and the best paragraph in the AI-assistant section. Add what the symptom is: pytest prints `PytestConfigWarning: Unknown config option: stocktake` and nothing else.
5. **Exit code 0 definition**: false for all-unread projects (6.3).
6. **"`STOCKTAKE_OFFLINE=1` force the skip"**: true for pytest; see 8.8.
7. **"Think of it as ... Needs StockTake installed? yes, as a dev dependency"**: no way shown today (Section 3, item 3).
8. **Install**: item 1 and 2 of the friction log.
9. **"Exit 1 on the first run is expected"** (AI section 4): confirmed on every real project I ran: 7, 11 and the two scratch projects all exited 1.
10. **"A project with no `node_modules` ... Run the install first"**: the note appeared exactly as described on the fresh clone (`7 unpinned`, "Run `npm install` (or `npm ci`)"), and the lock-file findings were unaffected. I did not run `npm ci` to confirm the seven resolve afterwards.
11. **Commands list**: every command listed exists and does what the comment says.

## 10 Suggestions for the product (prioritised)

**P0**

None. Nothing I ran made it report a project clean when it was not.

**P1**

1. **Make the vendored snippet show why it failed.** Change the README's last line and the docstring at the top of `stocktake_vendored.py` so the assertion carries the text. Better: ship a one-call helper in the vendored file that raises with the report. (9.2)
2. **Fix the CI step for Windows runners**: add `shell: bash` in the README YAML, and in `.github/workflows` if the same idiom is used there. (9.3)
3. **Decide what exit 0 means when nothing was checked and something was unread.** Options: exit 2 when `checked == 0` and `unread` is non-empty; or a new `complete: false` reason "no reader" that exits 2 unless `accept_unread` lists it (which already exists and is the right escape hatch). Whichever is chosen, make the README's definition of exit 0 true. (6.3)
4. **Say how to add StockTake as a dev dependency while it is unpublished** (a `requirements-dev.txt` line, a `pyproject.toml` `dependency-groups` entry or `uv add --dev git+...`). Test whichever you print. (Section 3, item 3)

**P2**

5. Put `pip install git+...` first in Install; keep the clone as "to work on StockTake itself". Drop `py -3.11` from the first block or say `python3`. (Section 3)
6. Name the symptom in the "silently does nothing" paragraph: `PytestConfigWarning: Unknown config option: stocktake`. Optionally suggest `-W error::pytest.PytestConfigWarning` for CI. (9.4)
7. Honour `STOCKTAKE_OFFLINE` in the CLI, or document that it is a plugin-only switch in `--help`. (8.8)
8. Print the unreadable-file message once, not on both streams. (6.4)
9. Headline counts findings, not packages: `11 vulnerable` was 8 packages. Say `11 vulnerable (8 packages)` or define the unit in the headline. The README explains it, but only in the `npm audit` comparison section.
10. Say which version clears *each* advisory, not only the one that clears all. For `electron 33.4.11` the line says `upgrade to 42.11.16 or newer`, nine major versions away, and an owner deciding whether to accept the risk for a quarter wants to know what the smallest hop is.
11. Allow ignoring by package and version in policy with a reason and a date (`ignore_package = "electron"`, `version = "33.4.11"`), alongside the per-advisory ids. Electron's 46 advisories make the per-id route 46 entries. (11)
12. Typo: `did you mean `exclude`?.` has an extra full stop. TOML errors could carry a line number.
13. Put a message after the dash in `FAILED stocktake_dependency_check - `.
14. Use local date for the report header, or label it UTC. (8.9)

## 11 Adopting StockTake in Can-AI

This section was written for the first trial's project. For this one, the project I am about to go back to is **Pixel Galaxy Studio** (`gbsnsgrckr/pixel_galaxy_studio_BCSS`, branch `main-24h1wy`, head `b7773f0`), so I answer for it. Section 11 of a report from another project should say which project it means.

- **Which route.** The project is a no-build static web app with an Electron shell, tested with Playwright and `npm run check`. It has no Python test suite, so route 1 and route 2 do not apply. Routes 3 and 4 do. The README's route table pointed me there correctly on the first read.
- **What it found today** (lock file only, no `node_modules`): 11 vulnerable findings in 8 packages: `tar 6.2.1` (12 advisories, 1 critical), `electron 33.4.11` (46), `extract-zip 2.0.1` (2, no fixed version named), `app-builder-lib 25.1.8`, `builder-util-runtime 9.2.10`, `glob 10.5.0`, `ip-address 10.7.2`, `minimatch` at four versions. Plus 233 outdated and, without `node_modules`, 7 unpinned. This list equals what `npm audit` says.
- **If wired into `npm run check`** (via the vendored file called from a unit test) it would fail on the first run, and no policy line available today makes it pass honestly: `extract-zip` has no fix; `electron` is nine majors away; `hold_back` does not cover vulnerabilities. The route would be 58 `ignore_advisories` entries (46 + 12) with a reason and a date each. Practically: use route 4 in CI (uploading SARIF, where findings are visible but do not block merges), and not the failing-test route until suggestion 11 exists.
- **What I did not do.** I did not change anything in the project, run `npm ci`, or add the file. Adoption belongs in that project's own work.

## 12 Questions I could not answer

1. Does the CI step work on a real `windows-latest` runner with `shell: bash` added? (I expect yes; not run.)
2. Do `uv add --dev git+...` or a `requirements-dev.txt` `stocktake @ git+...` line install the plugin correctly, so that `stocktake = true` works in a fresh clone? (`uv` is not installed here.)
3. Does the `git clone` + `pip install -e .` route on Install work from a stranger's point of view? I used the other route.
4. Python 3.11: I ran only the vendored file on 3.11; the CLI, plugin and `init` ran on 3.13.
5. Linux and macOS: nothing run. The cache path and the `~/.cache` claim are untested.
6. After `npm ci`, do the seven unpinned `package.json` ranges resolve and does the finding count stay the same?
7. What happens on a project with a SHA-pinned action, a Dockerfile, or a GitHub-release download? I did not build those fixtures.
8. How does it behave behind a corporate proxy that needs authentication? I only tested a closed port.

## 13 Reproduction

```bash
# environment (Windows; use python3 -m venv on Linux)
py -3.13 -m venv env
./env/Scripts/python -m pip install git+https://github.com/BlackCanyonSoftware/stocktake_BCS
./env/Scripts/stocktake --version                      # stocktake 0.1.0

# fixtures: docs/feedback/examples/w01 to w04, each with an EXPECTED.md
./env/Scripts/stocktake --root w01-pytest-two-vulnerable          # 2 vulnerable, exit 1
./env/Scripts/stocktake --root w02-node-only-with-workflow        # lodash twice + checkout@v2, exit 1
./env/Scripts/stocktake --root w03-clean-click                    # 1 outdated, exit 0
./env/Scripts/stocktake --root w04-only-unread-manifests; echo $? # 0 checked, exit 0  (section 6.3)

# route 1 (w01, in its own venv)
py -3.13 -m venv w01-pytest-two-vulnerable/.venv
w01-pytest-two-vulnerable/.venv/Scripts/python -m pip install pytest git+https://github.com/BlackCanyonSoftware/stocktake_BCS
printf 'stocktake = true\n' >> w01-pytest-two-vulnerable/pyproject.toml
(cd w01-pytest-two-vulnerable && .venv/Scripts/python -m pytest -q)   # 1 failed, 1 passed

# route 3 (w02, no Python in the project)
./env/Scripts/stocktake vendor w02-node-only-with-workflow
# save the README snippet as check_deps.py there, then:
py -3.11 w02-node-only-with-workflow/check_deps.py                # AssertionError, nothing else (9.2)
# do not use `python -I`: it removes the script's folder from sys.path and the import fails

# route 4 shell semantics
sh -c "./env/Scripts/stocktake --root w02-node-only-with-workflow --format sarif > out.sarif || [ \$? -eq 1 ]"; echo $?   # 0

# PowerShell parse failure (9.3): in a .ps1, run `& stocktake ... || [ $? -eq 1 ]` under powershell 5.1 and pwsh 7

# accuracy cross-checks
curl -s -X POST https://api.osv.dev/v1/query -d '{"package":{"name":"lodash","ecosystem":"npm"},"version":"4.17.15"}'
npm audit --package-lock-only --json     # in a folder with package-lock.json
# real projects, read-only: DayandNight_BCS (local); a scratch clone of the Pixel Galaxy Studio branch main-24h1wy
```

The scratch projects other than w01 to w04 (config-key, UTF-16, TOML and policy cases in section 8) were one-line files and are not stored; section 8 gives the content of each.
