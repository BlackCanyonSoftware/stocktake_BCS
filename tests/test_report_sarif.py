"""SARIF output: the shape, the judgement about what belongs in it, and one test that validates it against the official schema.

SARIF exists so that something *else* can read it — an editor, GitHub's code-scanning view — which makes "I believe this is valid" worth very
little. The last test in this module fetches the published SARIF 2.1.0 schema and validates against it. It is marked `network` and skips
when the schema cannot be fetched, like every other test here that needs the outside world.
"""

import json
import urllib.error
import urllib.request

import pytest

from stocktake.evaluate import evaluate
from stocktake.models import Dep, Report, Unread
from stocktake.report.sarif import LEVELS, POLICY_RULE, SCHEMA, UNREAD_RULE, as_sarif, render_sarif

from helpers import TODAY, FakeNet, advisory_detail, pin, registries

SARIF_LEVELS = {"none", "note", "warning", "error"}


def judged(tmp_path, deps, net, **kwargs):
    return evaluate(deps, registries(tmp_path, net), today=TODAY, **kwargs)


def everything(tmp_path):
    """A report with one finding of every shape SARIF has to carry, plus a policy problem and an unread manifest."""
    net = FakeNet(
        pypi={"bad": ("2.0", []), "gone": ("3.0", ["1.0"]), "old": ("2.0", []), "fine": ("1.0", [])},
        osv={("bad", "1.0"): ["GHSA-1"]},
        details={"GHSA-1": advisory_detail("a real problem", "CRITICAL", fixed=["1.5"], package="bad")},
    )
    deps = [
        pin("bad", "1.0", source="docker/dev/Dockerfile:12"),
        pin("gone", "1.0", source="requirements.txt:3"),
        pin("old", "1.0", source="pyproject.toml"),
        pin("fine", "1.0", source="pyproject.toml"),
        pin("loose", None, source="docker/dev/Dockerfile:14"),
        Dep("npm", "mystery", "1.0.0", "package.json"),
    ]
    report = judged(tmp_path, deps, net, unread=Unread(("go.mod",)))
    # Policy problems and notes are easier to attach here than to arrange through a config file for every test.
    return Report(
        findings=report.findings,
        policy_problems=("hold_back: old was accepted until 2026-01-01 and is due for a decision again (later)",),
        offline=report.offline,
        today=report.today,
        unread_manifests=report.unread_manifests,
        notes=("No Python environment was found for this project.",),
        config_source=".stocktake.toml",
    )


def results_of(log):
    return log["runs"][0]["results"]


def rule_ids(log):
    return [r["ruleId"] for r in results_of(log)]


# ---------- the shape ----------
def test_the_log_declares_itself_and_the_tool(tmp_path):
    log = as_sarif(everything(tmp_path))
    assert log["version"] == "2.1.0"
    assert log["$schema"] == SCHEMA
    driver = log["runs"][0]["tool"]["driver"]
    assert driver["name"] == "StockTake"
    assert driver["version"] and driver["informationUri"]


def test_every_rule_a_result_refers_to_is_declared(tmp_path):
    log = as_sarif(everything(tmp_path))
    declared = {rule["id"] for rule in log["runs"][0]["tool"]["driver"]["rules"]}
    assert set(rule_ids(log)) <= declared, "SARIF requires a rule for every ruleId used"
    assert all(rule["shortDescription"]["text"] and rule["fullDescription"]["text"] for rule in log["runs"][0]["tool"]["driver"]["rules"])


def test_no_rule_is_declared_that_nothing_uses(tmp_path):
    log = as_sarif(everything(tmp_path), "vulnerable")
    declared = {rule["id"] for rule in log["runs"][0]["tool"]["driver"]["rules"]}
    assert declared == set(rule_ids(log))


def test_every_level_is_one_sarif_knows(tmp_path):
    assert {r["level"] for r in results_of(as_sarif(everything(tmp_path)))} <= SARIF_LEVELS


# ---------- the judgement about what belongs in it ----------
def test_what_fails_a_build_is_an_error_and_what_merely_informs_is_a_note(tmp_path):
    by_rule = {r["ruleId"]: r["level"] for r in results_of(as_sarif(everything(tmp_path)))}
    assert by_rule["vulnerable"] == "error"
    assert by_rule["yanked"] == "error"
    assert by_rule[POLICY_RULE] == "error", "an overdue policy entry fails the build, so it belongs with the failures"
    assert by_rule["outdated"] == "note"
    assert by_rule["unpinned"] == "note"
    assert by_rule["unknown"] == "note"


def test_a_dependency_with_nothing_wrong_with_it_is_not_a_result(tmp_path):
    # A code-scanning view is a list of things to look at. 197 rows saying "this one is fine" is not that.
    log = as_sarif(everything(tmp_path))
    assert "current" not in rule_ids(log)
    assert "fine" not in json.dumps(log)


def test_a_held_dependency_is_not_shown_back_to_the_project_that_held_it(tmp_path):
    net = FakeNet(pypi={"held": ("2.0", [])})
    report = judged(tmp_path, [pin("held", "1.0")], net)
    held = Report(findings=(report.findings[0].__class__(report.findings[0].dep, "held", "info", "2.0"),), today=TODAY.isoformat())
    assert rule_ids(as_sarif(held)) == []


def test_an_unread_manifest_is_a_note_against_the_file_itself(tmp_path):
    result = next(r for r in results_of(as_sarif(everything(tmp_path))) if r["ruleId"] == UNREAD_RULE)
    assert result["level"] == "note"
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "go.mod"


def test_narrowing_the_report_narrows_the_log_the_same_way(tmp_path):
    report = everything(tmp_path)
    assert set(rule_ids(as_sarif(report, "vulnerable"))) == {"vulnerable", "yanked", POLICY_RULE}
    assert set(rule_ids(as_sarif(report, "outdated"))) == {"vulnerable", "yanked", "outdated", POLICY_RULE}
    assert set(rule_ids(as_sarif(report, "all"))) >= {"vulnerable", "yanked", "outdated", "unpinned", "unknown", UNREAD_RULE}


# ---------- locations ----------
def test_a_finding_is_located_at_the_line_it_came_from(tmp_path):
    result = next(r for r in results_of(as_sarif(everything(tmp_path))) if r["ruleId"] == "vulnerable")
    location = result["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == "docker/dev/Dockerfile"
    assert location["artifactLocation"]["uriBaseId"] == "%SRCROOT%"
    assert location["region"]["startLine"] == 12


def test_a_finding_from_a_file_with_no_line_has_no_region_rather_than_line_zero(tmp_path):
    result = next(r for r in results_of(as_sarif(everything(tmp_path))) if r["ruleId"] == "outdated")
    location = result["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == "pyproject.toml"
    assert "region" not in location


def test_a_policy_problem_is_located_at_the_config_file_that_caused_it(tmp_path):
    result = next(r for r in results_of(as_sarif(everything(tmp_path))) if r["ruleId"] == POLICY_RULE)
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == ".stocktake.toml"


def test_a_policy_problem_with_no_config_file_to_point_at_carries_no_location():
    report = Report(findings=(), policy_problems=("ignore_advisories: GHSA-1 needs a reason",), today="2026-10-30")
    result = results_of(as_sarif(report))[0]
    assert "locations" not in result, "an invented location would be worse than none"


def test_every_result_carries_a_fingerprint_so_an_alert_can_be_followed_between_runs(tmp_path):
    for result in results_of(as_sarif(everything(tmp_path))):
        assert result["partialFingerprints"]["stocktakeFinding"]


def test_two_declarations_of_one_package_are_told_apart_by_their_fingerprints(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")})
    deps = [pin("a", "1.0", source="package.json"), pin("a", "1.0", source="package-lock.json")]
    prints = {r["partialFingerprints"]["stocktakeFinding"] for r in results_of(as_sarif(judged(tmp_path, deps, net)))}
    assert len(prints) == 2


# ---------- messages ----------
def test_a_vulnerable_message_names_the_advisories_and_the_version_that_clears_them(tmp_path):
    result = next(r for r in results_of(as_sarif(everything(tmp_path))) if r["ruleId"] == "vulnerable")
    assert "GHSA-1" in result["message"]["text"]
    assert "Upgrade to 1.5 or newer." in result["message"]["text"]


def test_a_long_advisory_list_is_counted_rather_than_recited(tmp_path):
    ids = [f"GHSA-{i:04d}" for i in range(9)]
    net = FakeNet(pypi={"big": ("2.0", [])}, osv={("big", "1.0"): ids}, details={i: advisory_detail("x", "HIGH") for i in ids})
    text = results_of(as_sarif(judged(tmp_path, [pin("big", "1.0")], net)))[0]["message"]["text"]
    assert "and 4 more" in text and text.count("GHSA-") == 5


def test_an_uncheckable_dependency_carries_the_readers_reason(tmp_path):
    dep = Dep("GitHub", "o/r", None, ".github/workflows/ci.yml:9", "@abc", "ci", "pinned to a commit")
    text = results_of(as_sarif(judged(tmp_path, [dep], FakeNet())))[0]["message"]["text"]
    assert "pinned to a commit" in text


# ---------- the run itself ----------
def test_a_run_that_could_not_be_completed_says_so_where_sarif_puts_that(tmp_path):
    net = FakeNet()
    net.offline = True
    log = as_sarif(judged(tmp_path, [pin("a", "1.0")], net))
    invocation = log["runs"][0]["invocations"][0]
    assert invocation["executionSuccessful"] is False
    assert any("could not be completed" in n["message"]["text"] for n in invocation["toolExecutionNotifications"])


def test_a_note_about_the_run_is_not_dressed_up_as_a_finding(tmp_path):
    log = as_sarif(everything(tmp_path))
    notifications = log["runs"][0]["invocations"][0]["toolExecutionNotifications"]
    assert any("No Python environment" in n["message"]["text"] for n in notifications)
    assert not any("No Python environment" in r["message"]["text"] for r in results_of(log))


def test_a_successful_run_needs_no_notifications_at_all(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])})
    invocation = as_sarif(judged(tmp_path, [pin("a", "1.0")], net))["runs"][0]["invocations"][0]
    assert invocation["executionSuccessful"] is True
    assert "toolExecutionNotifications" not in invocation


def test_an_empty_report_is_still_a_valid_shaped_log():
    log = as_sarif(Report(findings=(), today="2026-10-30"))
    assert log["runs"][0]["results"] == []
    assert log["runs"][0]["tool"]["driver"]["rules"] == []


def test_the_rendered_log_is_json(tmp_path):
    assert json.loads(render_sarif(everything(tmp_path))) == as_sarif(everything(tmp_path))


def test_every_status_that_can_fail_a_build_has_a_level(tmp_path):
    """If a new status is added and forgotten here, it would silently vanish from the SARIF rather than appearing wrongly."""
    from stocktake.models import FAIL_STATUSES

    assert set(LEVELS) >= FAIL_STATUSES
    assert all(LEVELS[status] == "error" for status in FAIL_STATUSES)


# ---------- the official schema ----------
@pytest.mark.network
def test_the_log_validates_against_the_published_sarif_schema(tmp_path):
    """The point of SARIF is that something else reads it, so the only claim worth making is one a validator agrees with."""
    jsonschema = pytest.importorskip("jsonschema", reason="jsonschema is a dev dependency")
    try:
        with urllib.request.urlopen(SCHEMA, timeout=30) as response:  # noqa: S310 - a literal https URL in this package
            schema = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"cannot fetch the SARIF schema ({exc})")

    jsonschema.validate(instance=as_sarif(everything(tmp_path)), schema=schema)
    jsonschema.validate(instance=as_sarif(everything(tmp_path), "vulnerable"), schema=schema)
    jsonschema.validate(instance=as_sarif(Report(findings=(), today="2026-10-30")), schema=schema)
