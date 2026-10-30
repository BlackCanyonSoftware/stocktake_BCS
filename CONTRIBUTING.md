# Contributing to StockTake

This is the long version. [AGENTS.md](AGENTS.md) is the short one, and the rules that must never be broken are in both.

## Setting up

Python 3.11 or later. `uv` is the install path StockTake documents for its users, but the repository itself is developed with whatever is to hand:

```bash
git clone https://github.com/BlackCanyonSoftware/stocktake_BCS.git
cd stocktake_BCS
py -3.11 -m venv .venv                              # python3.11 -m venv on macOS and Linux
./.venv/Scripts/python -m pip install -e ".[dev]"   # .venv/bin/python elsewhere
./.venv/Scripts/python -m pytest
```

The `dev` extra is `pytest`, `ruff`, `mypy` and `jsonschema`. The last is there for one test, which validates the SARIF output against the published schema.

## The commands

| | |
|---|---|
| `python -m pytest` | the whole suite, including the live check against the real registries |
| `python -m pytest -m "not network"` | everything that does not need the outside world |
| `STOCKTAKE_OFFLINE=1 python -m pytest` | the same, through StockTake's own offline switch |
| `python -m ruff check .` | lint |
| `python -m ruff format .` | format |
| `python -m mypy` | type check, strict, over `src` |
| `python -m stocktake` | run StockTake against itself |
| `stocktake vendor vendored/` | **after any change to the core**, or a test will fail |

All four checks have to pass before a commit. CI runs them on Windows and Linux, on 3.11 and 3.13.

## The one easily-missed step

The core is also published as a single self-contained file, generated into `vendored/` and committed so that a test can prove it is current. **Change anything under `src/stocktake/` and you must run `stocktake vendor vendored/`.** A `ruff format` pass is enough to make the committed copy stale, and `tests/test_vendor.py` will tell you so.

That also means the core carries two constraints it would not otherwise have, both enforced by the generator refusing to emit:

- **No two core modules may define the same top-level name.** In one flat file the second silently wins, which gives wrong answers rather than crashes.
- **No core module may import something the copy leaves out** — the command line, `init_project`, or the pytest plugin.

## Where things go

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) is the full picture. The short version, and the boundaries that matter:

- `readers/` turn project files into `Dep`s and **never touch the network**.
- `registries/` answer questions about names and **never touch the project**.
- `report/` is a pure function of a `Report`: nothing in it re-reads a file or asks a registry anything.
- `check.py` owns the fail/warn/skip rules, once. The command line and the pytest plugin both go through it, so a project's test suite can never disagree with its own command line.
- `cli.py` is the only module that prints or decides an exit code.
- `pytest_plugin.py` is the only module that imports pytest, and it is only ever imported under pytest.

### Adding an ecosystem

One module in `readers/`, one in `registries/`, an import line in each package's `__init__.py`, and a guard test. Nothing existing changes. See [ADR 0003](docs/adr/0003-readers-and-registry-clients-as-separate-interfaces.md), and the "Adding an ecosystem" section of ARCHITECTURE.md for the shape of a reader.

**Every reader needs a guard test**, and it is not optional. The pattern: count what the fixture declares using a regular expression written independently of the reader, count what the reader found, and fail if they differ. That is what caught `uv tool install maigret==0.6.6` being invisible in the code StockTake grew out of, and a clean-looking report that quietly missed half a project is the worst way this tool can fail.

## Testing

- **No test touches the real network, clock or filesystem** outside `tmp_path`, except the one marked `network` — and that one skips rather than fails when the registries cannot be reached.
- `tests/helpers.py` has `FakeNet`, which stands in for PyPI, npm, GitHub and OSV and **records the URLs it was asked for**. That is how a test proves a request was *not* made, which is the only way to check that the cache works or that a disabled ecosystem stays quiet.
- The pytest plugin is tested through `pytester`, which runs a real pytest in a scratch project. Assert on what a project's suite actually sees, not on the plugin's internals.
- Test names are sentences that state the expected behaviour. They are long, and that is deliberate: a failure should be readable without opening the file.
- A bug fix starts with a test that reproduces it. All three bugs fixed so far were found by running the tool against real projects, and each one has a regression test naming where it came from.

## Style

- **Ruff and mypy decide**, so there is nothing to argue about: 140 columns, strict typing over `src`. Fix a warning rather than suppressing it; a suppression gets a comment saying why.
- **Comments say why, not what.** The code says what it does. A comment earns its place by recording a decision, a trap, or something found the hard way — most of the comments in this repository exist because something was wrong once.
- **Name things so the next reader does not have to guess.** `normalize` and `registry_name` are different functions for a reason, and that reason is in both docstrings.
- **Never name anything `test*` in the package.** pytest collects it, and the first test module that imports it fails for returning a value.
- Module docstrings explain what the module is for and what decision shaped it, with a link to the ADR where there is one.

## The rules that are not up for negotiation

- **It never edits a dependency.** Not with a flag, not with a confirmation. The furthest it may go is printing the edit it would make.
- **It never executes anything it found.** No importing a scanned package, no running a lockfile's scripts, no shelling out to a package manager.
- **Only package names and versions leave the machine.** No paths, no file contents, no telemetry, ever.
- **A registry that cannot be reached is `unknown`, never clean.** Getting this wrong turns a network blip into a false all-clear, which is worse than any false positive.
- **Only unsafe findings fail a build.** Being behind warns. See [ADR 0004](docs/adr/0004-only-unsafe-findings-fail-the-build.md) — this is the decision the whole product rests on, and "it would be more thorough to fail on X" has already been considered and rejected.
- **The runtime core depends on nothing.** `packaging` is used when importable and has a fallback; a test enforces the rest.
- **Never weaken a test to get a passing run.** If a test is wrong, say why before changing it.

## Decisions

Anything significant gets an [Architecture Decision Record](docs/adr/): context, the options actually considered, the decision, and the consequences including what it costs. Several of them exist because a first attempt was wrong, and they say so — that is what they are for. Read the index before proposing a change to how something fundamental works; the argument may already be there.

## Commits

- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`), and the body says **why**.
- Small and focused. Never mix formatting with behaviour.
- Docs are updated in the same commit as the change they describe.
- The main branch stays working.

## Before you call something done

1. It meets what was asked.
2. Tests cover the new behaviour, and the whole suite passes.
3. `ruff check`, `ruff format --check` and `mypy` are clean.
4. You ran it — on a real project, not only on a fixture. Every bug found so far was found that way.
5. `stocktake vendor vendored/` if the core changed.
6. Every doc the change affects is updated, in the same commit.
7. No leftover debug code, commented-out code, or untracked TODOs. Every `TODO` has a line in [docs/ROADMAP.md](docs/ROADMAP.md).
8. If something is unverified, the report says so in those words.
