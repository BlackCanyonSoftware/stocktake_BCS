"""StockTake's dependency check, as part of this project's own test suite.

Written by `stocktake init`. It is yours now, so edit it freely.

It reads what this project pins, asks the public registries whether a newer release exists and whether the pinned one has a known security
advisory, and then:

- **fails** on a vulnerable or withdrawn release, or on a policy entry in `.stocktake.toml` whose `until` date has passed;
- **warns** in the test summary when something merely has a newer release — being behind is not a failure;
- **skips**, rather than failing, when the registries cannot be reached, or when `STOCKTAKE_OFFLINE` is set.

Only package names and versions leave this machine. No file is ever modified. Answers are cached for six hours, so running the suite
repeatedly costs nothing. Run `stocktake` for the full report, or `stocktake --only vulnerable` for just what must be fixed.
"""

from stocktake.pytest_plugin import assert_dependencies_are_safe


def test_dependencies_have_no_known_vulnerabilities(pytestconfig):
    assert_dependencies_are_safe(pytestconfig.rootpath)
