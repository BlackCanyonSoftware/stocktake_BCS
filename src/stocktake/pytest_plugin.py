"""StockTake as part of a project's own pytest suite.

**Installing the package does not switch this on.** A dependency that silently added a network-touching test to somebody's suite would be a
bad guest, and would fail builds nobody asked it to fail ([ADR 0007](adr/0007-the-pytest-plugin-is-opt-in.md)). A project opts in with one
line in its pytest configuration:

    [tool.pytest.ini_options]
    stocktake = true

or with `--stocktake` for a single run. `--no-stocktake` switches it off again for one run without editing anything.

A project that would rather own the test file runs `stocktake init` instead and gets the same rules through `assert_dependencies_are_safe`.
Either way the rules come from `stocktake.check`, so the two paths cannot drift apart, and neither can drift from the command line.

This is the only module in the package that imports pytest, and it is only ever imported under pytest.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

import pytest

from stocktake.check import failure_text, incomplete_text, run_check, skip_reason, update_warning
from stocktake.config import ConfigError
from stocktake.models import DependencyUpdateAvailable

OFFLINE_ENV = "STOCKTAKE_OFFLINE"
ITEM_NAME = "stocktake_dependency_check"
MARKER = "stocktake"
OPTION = "stocktake"

HELP = "run StockTake's dependency check as part of this suite"


def assert_dependencies_are_safe(root: Path | str | None = None, **kwargs: Any) -> None:
    """Run StockTake's check and apply its rules.

    Fails on anything unsafe, warns in the test summary on anything merely old, and skips — rather than failing — when the registries cannot
    be reached or `STOCKTAKE_OFFLINE` is set.

    It also fails when a dependency file could not be read, which is not an unsafe finding but is the check not having happened. A skip would
    be the softer answer and the wrong one: on the command line that case is exit 2, and a suite has no exit code to carry the difference, so
    a skip here would turn a project that is not being checked into a green run that says so in small print (docs/adr/0009).

    `root` is the project to check; pass pytest's `pytestconfig.rootpath` for it. Any other keyword goes straight to `run_check`, which is how
    a test can hand it a fake network or a fixed date.
    """
    if os.environ.get(OFFLINE_ENV):
        pytest.skip(f"{OFFLINE_ENV} is set")

    report = run_check(Path(root) if root is not None else Path.cwd(), **kwargs)

    reason = skip_reason(report)
    if reason is not None:
        pytest.skip(reason)

    warning = update_warning(report)
    if warning is not None:
        warnings.warn(DependencyUpdateAvailable(warning), stacklevel=2)

    # The incomplete message comes first when both apply: it says how much of what follows to trust.
    trouble = [text for text in (incomplete_text(report), failure_text(report)) if text is not None]
    if trouble:
        # Raised rather than asserted. `assert` vanishes under `python -O`, which would quietly turn the whole check off and leave a suite
        # passing for the wrong reason. pytest reports an AssertionError exactly the same way.
        raise AssertionError("\n".join(trouble))


# ---------------- the plugin proper ----------------
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("stocktake", "StockTake's dependency check")
    group.addoption("--stocktake", action="store_true", default=False, help=HELP)
    group.addoption(
        "--no-stocktake", action="store_true", default=False, help="do not run it this time, even if this project switches it on"
    )
    parser.addini(OPTION, HELP, type="bool", default=False)


def enabled(config: pytest.Config) -> bool:
    """Whether this project asked for the check. Off unless it did."""
    if config.getoption("no_stocktake"):
        return False
    return bool(config.getoption(OPTION) or config.getini(OPTION))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", f"{MARKER}: StockTake's dependency check, which asks the public registries about this project")


class DependencyCheckItem(pytest.Item):
    """The dependency check, as one test at the end of the session."""

    def runtest(self) -> None:
        assert_dependencies_are_safe(self.config.rootpath)

    def reportinfo(self) -> tuple[Path, int | None, str]:
        return self.config.rootpath, None, "StockTake dependency check"

    def repr_failure(self, excinfo: pytest.ExceptionInfo[BaseException], style: Any = None) -> str:
        """The report is the message. A Python traceback through StockTake's own internals tells the reader nothing useful."""
        if isinstance(excinfo.value, AssertionError):
            return str(excinfo.value)
        if isinstance(excinfo.value, ConfigError):
            return f"StockTake could not run: {excinfo.value}"
        return str(super().repr_failure(excinfo, style))


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(session: pytest.Session, config: pytest.Config, items: list[pytest.Item]) -> None:
    """Add the check to the end of the session, before pytest's own `-k` and `-m` filtering runs, so both still apply to it."""
    if not enabled(config):
        return
    # The explicit nodeid matters: parented on the session, the default would be "::stocktake_dependency_check", with an empty path in front
    # of it in every verbose line and every JUnit report.
    item = DependencyCheckItem.from_parent(session, name=ITEM_NAME, nodeid=ITEM_NAME)
    item.add_marker(MARKER)
    items.append(item)
