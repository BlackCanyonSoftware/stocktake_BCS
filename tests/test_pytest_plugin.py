"""The plugin, as a project's own suite actually sees it.

Driven with pytest's `pytester`, which runs a real pytest in a scratch project. Asserting on what a suite sees is worth far more here than
asserting on the plugin's internals: the whole promise of this milestone is "add one line, run pytest, nothing else changes".

The registries are never reached: `STOCKTAKE_OFFLINE` makes the check skip, which is exactly the behaviour US-011 asks for and leaves these
tests fast and deterministic. The rules themselves are tested in `test_check.py`.
"""

import pytest

from stocktake.pytest_plugin import ITEM_NAME, OFFLINE_ENV

EXISTING_SUITE = """
def test_something_this_project_already_had():
    assert True
"""

PYPROJECT = """
[project]
name = "scratch"
version = "0.1.0"
dependencies = ["flask>=2"]
"""


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Every test in this module runs with the network declared unreachable, so the injected check skips instead of asking anything."""
    monkeypatch.setenv(OFFLINE_ENV, "1")


def scratch(pytester, ini=""):
    """A project with a suite of its own, and whatever pytest configuration the test wants."""
    pytester.makepyfile(test_existing=EXISTING_SUITE)
    pytester.path.joinpath("pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    pytester.path.joinpath("pytest.ini").write_text(f"[pytest]\n{ini}", encoding="utf-8")
    return pytester


def test_installing_stocktake_does_not_add_anything_to_a_suite(pytester):
    """The decision in ADR 0007. A dependency that silently added a network-touching test would be a bad guest."""
    result = scratch(pytester).runpytest()
    result.assert_outcomes(passed=1)
    assert ITEM_NAME not in result.stdout.str()


def test_one_line_in_the_pytest_config_switches_it_on(pytester):
    result = scratch(pytester, "stocktake = true\n").runpytest("-v")
    result.assert_outcomes(passed=1, skipped=1)
    result.stdout.fnmatch_lines([f"*{ITEM_NAME}*SKIPPED*"])


def test_the_suite_still_passes_when_the_check_cannot_be_made(pytester):
    """US-011. A plane, a locked-down runner or a registry outage must not turn somebody's build red."""
    result = scratch(pytester, "stocktake = true\n").runpytest()
    result.assert_outcomes(passed=1, skipped=1)
    assert result.ret == 0


def test_it_can_be_switched_on_for_a_single_run_without_editing_anything(pytester):
    result = scratch(pytester).runpytest("--stocktake")
    result.assert_outcomes(passed=1, skipped=1)


def test_it_can_be_switched_off_for_a_single_run_without_editing_anything(pytester):
    result = scratch(pytester, "stocktake = true\n").runpytest("--no-stocktake")
    result.assert_outcomes(passed=1)


def test_the_check_carries_a_marker_so_a_suite_can_deselect_it(pytester):
    result = scratch(pytester, "stocktake = true\n").runpytest("-m", "not stocktake")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*1 deselected*"])


def test_the_check_can_be_selected_on_its_own(pytester):
    result = scratch(pytester, "stocktake = true\n").runpytest("-m", "stocktake")
    result.assert_outcomes(skipped=1)


def test_the_marker_is_registered_so_strict_markers_does_not_complain(pytester):
    result = scratch(pytester, "stocktake = true\naddopts = --strict-markers\n").runpytest()
    result.assert_outcomes(passed=1, skipped=1)


def test_the_check_runs_last_so_a_suites_own_failures_are_read_first(pytester):
    pytester.makepyfile(test_existing="def test_fails():\n    assert False\n")
    pytester.path.joinpath("pytest.ini").write_text("[pytest]\nstocktake = true\n", encoding="utf-8")
    result = pytester.runpytest("-v")
    result.assert_outcomes(failed=1, skipped=1)
    # The progress lines only: the short summary at the end would otherwise be mistaken for the running order.
    progress = [line for line in result.outlines if "%]" in line]
    assert "test_fails" in progress[0] and ITEM_NAME in progress[-1]


def test_a_project_with_no_tests_of_its_own_still_gets_the_check(pytester):
    pytester.path.joinpath("pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    pytester.path.joinpath("pytest.ini").write_text("[pytest]\nstocktake = true\n", encoding="utf-8")
    result = pytester.runpytest()
    result.assert_outcomes(skipped=1)


# ---------- the one-file path, end to end ----------
def test_the_file_written_by_init_does_the_same_thing(pytester):
    """US-010, for real: `stocktake init` writes a file, `pytest` picks it up, and the rules are the same ones."""
    from stocktake.init_project import init_project

    pytester.path.joinpath("pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    pytester.path.joinpath("pytest.ini").write_text("[pytest]\n", encoding="utf-8")  # the plugin is NOT switched on
    written = init_project(pytester.path)
    assert [w.outcome for w in written] == ["written", "written"]

    result = pytester.runpytest("-v")
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*test_dependencies*SKIPPED*"])


def test_the_written_file_and_the_plugin_do_not_both_run(pytester):
    """A project that ran `init` and then also switched the plugin on would check itself twice. Worth knowing; it is not an error."""
    from stocktake.init_project import init_project

    pytester.path.joinpath("pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    pytester.path.joinpath("pytest.ini").write_text("[pytest]\nstocktake = true\n", encoding="utf-8")
    init_project(pytester.path)
    result = pytester.runpytest()
    result.assert_outcomes(skipped=2)
