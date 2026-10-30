"""The rules, in the one place they live: what fails a build, what only warns, and what cannot be judged at all.

Both the command line and the pytest plugin go through these, which is the point of the module. Tested here against a fake network so the
rules can be exercised without any of the wiring around them.
"""

from datetime import date

import pytest

from stocktake.check import failure_text, run_check, skip_reason, update_warning
from stocktake.config import Config, ConfigError
from stocktake.models import DependencyUpdateAvailable
from stocktake.policy import HOLD, Policy, PolicyEntry
from stocktake.pytest_plugin import OFFLINE_ENV, assert_dependencies_are_safe

from helpers import TODAY, FakeNet, advisory_detail, registries


def project(tmp_path, name="project", dockerfile="FROM x\nRUN pip install a==1.0\n"):
    root = tmp_path / name
    root.mkdir()
    (root / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    return root


def checked(tmp_path, root, net, **kwargs):
    kwargs.setdefault("installed", lambda name: None)
    return run_check(root, registries=registries(tmp_path, net), today=TODAY, **kwargs)


# ---------- one run ----------
def test_a_run_reads_the_project_asks_the_registries_and_judges_the_answers(tmp_path):
    report = checked(tmp_path, project(tmp_path), FakeNet(pypi={"a": ("2.0", [])}))
    assert [(f.dep.name, f.status) for f in report.findings] == [("a", "outdated")]
    assert report.today == TODAY.isoformat()


def test_a_run_uses_the_projects_own_config(tmp_path):
    root = project(tmp_path)
    (root / ".stocktake.toml").write_text('[[policy.hold_back]]\npackage = "a"\nreason = "later"\nuntil = 2026-12-01\n', encoding="utf-8")
    report = checked(tmp_path, root, FakeNet(pypi={"a": ("2.0", [])}))
    assert report.findings[0].status == "held"


def test_a_config_can_be_handed_in_instead_of_read_from_the_project(tmp_path):
    config = Config(policy=Policy((PolicyEntry(HOLD, "a", "handed in", date(2026, 12, 1)),)))
    report = checked(tmp_path, project(tmp_path), FakeNet(pypi={"a": ("2.0", [])}), config=config)
    assert report.findings[0].status == "held"


def test_a_named_environment_that_does_not_exist_stops_the_run_rather_than_falling_back(tmp_path):
    # Somebody who went to the trouble of naming an environment does not want a silent fallback to a different one.
    root = project(tmp_path)
    with pytest.raises(ConfigError, match="no Python environment found at"):
        run_check(root, registries=registries(tmp_path, FakeNet()), environment=str(tmp_path / "nowhere"), today=TODAY)


def test_an_unusable_config_stops_the_run(tmp_path):
    root = project(tmp_path)
    (root / ".stocktake.toml").write_text("[[policy.hold_back]\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid TOML"):
        checked(tmp_path, root, FakeNet())


# ---------- the three questions ----------
def test_nothing_unsafe_means_nothing_to_say(tmp_path):
    report = checked(tmp_path, project(tmp_path), FakeNet(pypi={"a": ("1.0", [])}))
    assert skip_reason(report) is None
    assert update_warning(report) is None
    assert failure_text(report) is None


def test_a_newer_release_is_a_warning_that_names_what_moved(tmp_path):
    report = checked(tmp_path, project(tmp_path), FakeNet(pypi={"a": ("2.0", [])}))
    warning = update_warning(report)
    assert warning is not None
    assert "1 dependencies have a newer release: a 1.0->2.0" in warning
    assert "run `stocktake`" in warning, "a warning that does not say how to see more is half a warning"
    assert failure_text(report) is None, "being behind is not a failure"


def test_a_long_list_of_outdated_dependencies_is_counted_rather_than_recited(tmp_path):
    names = [f"pkg{i:02d}" for i in range(20)]
    root = project(tmp_path, dockerfile="FROM x\n" + "".join(f"RUN pip install {n}==1.0\n" for n in names))
    report = checked(tmp_path, root, FakeNet(pypi={n: ("2.0", []) for n in names}))
    warning = update_warning(report)
    assert warning is not None
    assert warning.startswith("20 dependencies have a newer release:")
    assert warning.count("->") == 12 and " ..." in warning


def test_something_vulnerable_is_a_failure_carrying_the_report(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad", "HIGH")})
    failure = failure_text(checked(tmp_path, project(tmp_path), net))
    assert failure is not None
    assert "VULNERABLE (fix these)" in failure and "GHSA-1" in failure
    assert "OUTDATED" not in failure, "a failure that also lists the merely-old is one people learn to skim"


def test_an_overdue_policy_entry_is_a_failure_too(tmp_path):
    root = project(tmp_path)
    (root / ".stocktake.toml").write_text('[[policy.hold_back]]\npackage = "a"\nreason = "later"\nuntil = 2026-01-01\n', encoding="utf-8")
    failure = failure_text(checked(tmp_path, root, FakeNet(pypi={"a": ("2.0", [])})))
    assert failure is not None and "POLICY:" in failure


def test_being_unable_to_reach_the_registries_is_a_skip_and_not_a_failure(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])})
    net.offline = True
    report = checked(tmp_path, project(tmp_path), net)
    reason = skip_reason(report)
    assert reason is not None and "cannot reach the registries" in reason
    assert failure_text(report) is None


# ---------- the same rules, as a test suite sees them ----------
def test_a_suite_fails_on_something_vulnerable_and_the_report_is_the_message(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad", "HIGH")})
    with pytest.raises(AssertionError, match="VULNERABLE"):
        assert_dependencies_are_safe(project(tmp_path), registries=registries(tmp_path, net), installed=lambda name: None, today=TODAY)


def test_a_suite_warns_rather_than_failing_on_something_merely_old(tmp_path):
    net = FakeNet(pypi={"a": ("2.0", [])})
    with pytest.warns(DependencyUpdateAvailable, match="a 1.0->2.0"):
        assert_dependencies_are_safe(project(tmp_path), registries=registries(tmp_path, net), installed=lambda name: None, today=TODAY)


def test_a_suite_skips_when_the_registries_cannot_be_reached(tmp_path):
    net = FakeNet()
    net.offline = True
    with pytest.raises(pytest.skip.Exception, match="cannot reach the registries"):
        assert_dependencies_are_safe(project(tmp_path), registries=registries(tmp_path, net), installed=lambda name: None, today=TODAY)


def test_a_suite_skips_without_asking_anything_when_told_it_is_offline(tmp_path, monkeypatch):
    monkeypatch.setenv(OFFLINE_ENV, "1")
    net = FakeNet(pypi={"a": ("1.0", [])})
    with pytest.raises(pytest.skip.Exception, match=OFFLINE_ENV):
        assert_dependencies_are_safe(project(tmp_path), registries=registries(tmp_path, net), installed=lambda name: None, today=TODAY)
    assert net.calls == [], "being told we are offline means not trying"


# ---------- what the run says about itself ----------
# Found by running the tool against four of the author's real projects. Each of these was wrong there before it was right.
def test_a_project_with_no_python_in_it_is_not_told_to_find_a_python_environment(tmp_path):
    """A pure Node project was being advised to pass --environment, which cannot help it and makes the rest of the report look careless."""
    root = tmp_path / "node-only"
    root.mkdir()
    (root / "package.json").write_text('{"name": "x", "dependencies": {"left-pad": "^1.0.0"}}', encoding="utf-8")

    report = run_check(root, registries=registries(tmp_path, FakeNet(npm={"left-pad": "1.3.0"})), today=TODAY)
    assert not any("Python environment" in note for note in report.notes)
    assert any("npm install" in note for note in report.notes), "and it should be told the thing that would help"


def test_a_python_range_that_went_unresolved_does_ask_for_an_environment(tmp_path):
    root = tmp_path / "python-only"
    root.mkdir()
    (root / "requirements.txt").write_text("django>=5.2\n", encoding="utf-8")

    report = run_check(root, registries=registries(tmp_path, FakeNet(pypi={"django": ("5.2.1", [])})), today=TODAY)
    assert any("Python environment" in note for note in report.notes)
    assert not any("npm install" in note for note in report.notes)


def test_a_project_with_both_problems_is_told_about_both(tmp_path):
    root = tmp_path / "both"
    root.mkdir()
    (root / "requirements.txt").write_text("django>=5.2\n", encoding="utf-8")
    (root / "package.json").write_text('{"name": "x", "dependencies": {"left-pad": "^1.0.0"}}', encoding="utf-8")

    net = FakeNet(pypi={"django": ("5.2.1", [])}, npm={"left-pad": "1.3.0"})
    notes = run_check(root, registries=registries(tmp_path, net), today=TODAY).notes
    assert len(notes) == 2


def test_a_dockerfiles_unpinned_install_asks_for_nothing(tmp_path):
    """It is about what the image will build when it is built, not about which environment StockTake looked in."""
    root = tmp_path / "image"
    root.mkdir()
    (root / "Dockerfile").write_text("FROM python:3.12\nRUN pip install ruff\n", encoding="utf-8")

    report = run_check(root, registries=registries(tmp_path, FakeNet(pypi={"ruff": ("0.17.3", [])})), today=TODAY)
    assert report.notes == ()
    assert report.counts["unpinned"] == 1


def test_an_npm_range_that_is_not_installed_says_node_modules_and_not_this_environment(tmp_path):
    """ "not installed in this environment" reads as a Python environment, which means nothing to somebody reading a Node project's report."""
    root = tmp_path / "node-only"
    root.mkdir()
    (root / "package.json").write_text('{"name": "x", "dependencies": {"left-pad": "^1.0.0"}}', encoding="utf-8")

    report = run_check(root, registries=registries(tmp_path, FakeNet(npm={"left-pad": "1.3.0"})), today=TODAY)
    finding = next(f for f in report.findings if f.dep.name == "left-pad")
    assert finding.status == "unpinned"
    assert finding.note == "not installed in node_modules, and no version is pinned"


def test_the_caller_that_supplied_the_answers_is_given_no_advice_about_finding_them(tmp_path):
    root = tmp_path / "both"
    root.mkdir()
    (root / "requirements.txt").write_text("django>=5.2\n", encoding="utf-8")
    net = FakeNet(pypi={"django": ("5.2.1", [])})
    assert run_check(root, registries=registries(tmp_path, net), installed=lambda name: None, today=TODAY).notes == ()


def test_a_suite_passes_quietly_when_everything_is_current(tmp_path, recwarn):
    net = FakeNet(pypi={"a": ("1.0", [])})
    assert_dependencies_are_safe(project(tmp_path), registries=registries(tmp_path, net), installed=lambda name: None, today=TODAY)
    assert [w for w in recwarn if issubclass(w.category, DependencyUpdateAvailable)] == []
