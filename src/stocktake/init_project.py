"""`stocktake init`: write the one test file a project needs, and a starter config.

For a project that would rather own its test file than switch on a plugin. The file is four lines, it is readable, and it is theirs to edit
afterwards — but the rules it applies are still the ones in `stocktake.check`, so it cannot drift from what the command line says.

Nothing is ever overwritten without being asked. A file that already exists is left exactly as it is and reported as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from stocktake.config import CONFIG_NAME

TEST_FILENAME = "test_dependencies.py"
TEMPLATE_PACKAGE = "stocktake.templates"
TEMPLATE_NAME = "dependency_test_template.py"

WRITTEN = "written"
EXISTS = "exists"
FAILED = "failed"

STARTER_CONFIG = """# StockTake's configuration for this project. Every key is optional, and the
# defaults are what a project with no config at all gets.
# https://github.com/BlackCanyonSoftware/stocktake_BCS

# Which readers to run. Leave this out and they all run.
# ecosystems = ["python", "binaries"]

# Folders and files to skip, added to the built-in defaults (.git, .venv, node_modules, ...).
# exclude = ["vendor", "tests/fixtures"]

# Manifests you know StockTake cannot read yet. This stops the notice in the report;
# they still appear in `stocktake --format json`, so the gap never becomes invisible.
# accept_unread = ["go.mod"]

# Where this project's Python environment is, if it is not ./.venv. Needed only for
# dependencies declared as a range, which are checked at the version actually installed.
# environment = "tools/env"

# [cache]
# ttl_hours = 6

# Decisions you have made. Every entry needs a reason and a date to make it again:
# an entry past its `until` date FAILS the check until it is renewed, so
# "ignore it for now" cannot quietly become "ignore it forever".

# [[policy.ignore_advisories]]
# id = "GHSA-xxxx-xxxx-xxxx"
# reason = "only reachable through a feature we do not use"
# until = 2026-12-01

# [[policy.hold_back]]
# package = "pillow"
# reason = "12.4 changes the PNG writer; rebuild the logo samples first"
# until = 2026-12-01
"""


@dataclass(frozen=True, slots=True)
class Written:
    """What happened to one file."""

    path: Path
    outcome: str  # WRITTEN | EXISTS | FAILED
    detail: str = ""


def template_source() -> str:
    """The text of the test file `init` writes, read from the installed package.

    Not named `test_file_template`: pytest collects anything called `test*`, so a name like that gets picked up as a test by any test module
    that imports it, and then fails for returning a value.
    """
    return resources.files(TEMPLATE_PACKAGE).joinpath(TEMPLATE_NAME).read_text(encoding="utf-8")


def tests_directory(root: Path) -> Path:
    """Where this project keeps its tests: whichever of `tests/` and `test/` already exists, else `tests/`."""
    for name in ("tests", "test"):
        if (root / name).is_dir():
            return root / name
    return root / "tests"


def _write(path: Path, text: str, force: bool) -> Written:
    if path.exists() and not force:
        return Written(path, EXISTS, "left alone; --force overwrites")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return Written(path, FAILED, str(exc))
    return Written(path, WRITTEN)


def init_project(root: Path, tests_dir: Path | None = None, force: bool = False) -> list[Written]:
    """Write the test file and a starter config. Returns what happened to each, in the order attempted."""
    target = tests_dir if tests_dir is not None else tests_directory(root)
    return [
        _write(target / TEST_FILENAME, template_source(), force),
        _write(root / CONFIG_NAME, STARTER_CONFIG, force),
    ]
