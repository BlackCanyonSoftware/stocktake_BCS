"""The decision table: which findings fail, which warn, and which are honestly admitted to be unknown.

This is the heart of the product (docs/adr/0004). Everything here runs with the network faked, which is only possible because `evaluate()`
is handed its registries rather than building them.
"""

from datetime import date

from stocktake.evaluate import evaluate
from stocktake.models import Advisory, Dep, Unread
from stocktake.policy import HOLD, IGNORE, Policy, PolicyEntry
from stocktake.registries import OfflineError

from helpers import TODAY, FakeNet, advisory_detail, by_name, pin, registries

LATER = date(2026, 12, 1)
EARLIER = date(2026, 10, 1)


def judged(tmp_path, deps, net, policy=None, today=TODAY, unread=None):
    return evaluate(deps, registries(tmp_path, net), policy, today, unread)


def test_every_kind_of_finding_is_told_apart(tmp_path):
    net = FakeNet(
        pypi={"pillow": ("12.4.0", []), "numpy": ("2.5.3", []), "requests": ("2.40.0", []), "oldpkg": ("3.0", ["2.0"])},
        osv={("requests", "2.34.2"): ["GHSA-aaaa"]},
        details={"GHSA-aaaa": advisory_detail("Header injection in redirects", "HIGH", ["CVE-2026-1"], ["2.35.0", "2.34.9"], "requests")},
        github={"mostlygeek/llama-swap": "v263"},
    )
    deps = [
        pin("pillow", "12.3.0"),
        pin("numpy", "2.5.3"),
        pin("requests", "2.34.2"),
        pin("oldpkg", "2.0"),
        pin("pytest", None),
        pin("nothere", "1.0"),
        Dep("GitHub", "mostlygeek/llama-swap", "262", "Dockerfile:1"),
    ]
    got = by_name(judged(tmp_path, deps, net))

    assert (got["pillow"].status, got["pillow"].severity, got["pillow"].update, got["pillow"].latest) == (
        "outdated",
        "warn",
        "minor",
        "12.4.0",
    )
    assert (got["numpy"].status, got["numpy"].severity) == ("current", "ok")
    assert (got["requests"].status, got["requests"].severity) == ("vulnerable", "fail")
    assert got["requests"].advisories == (
        Advisory(
            id="GHSA-aaaa", severity="HIGH", summary="Header injection in redirects", aliases=("CVE-2026-1",), fixed=("2.34.9", "2.35.0")
        ),
    )
    assert (got["oldpkg"].status, got["oldpkg"].severity) == ("yanked", "fail")
    assert (got["pytest"].status, got["pytest"].severity) == ("unpinned", "info")
    assert got["nothere"].status == "unknown"
    assert (got["mostlygeek/llama-swap"].status, got["mostlygeek/llama-swap"].update) == ("outdated", "major")


def test_being_behind_is_not_a_failure_but_being_vulnerable_is(tmp_path):
    safe = FakeNet(pypi={"a": ("2.0", []), "b": ("1.0", [])})
    assert judged(tmp_path, [pin("a", "1.0"), pin("b", "1.0"), pin("c", None)], safe).failed is False

    unsafe = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")})
    assert judged(tmp_path, [pin("a", "1.0")], unsafe).failed is True


def test_a_withdrawn_release_fails_even_when_it_is_the_newest_one(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", ["1.0"])})
    finding = by_name(judged(tmp_path, [pin("a", "1.0")], net))["a"]
    assert (finding.status, finding.severity) == ("yanked", "fail")


def test_an_unpinned_dependency_says_which_kind_of_uncertainty_it_is(tmp_path):
    net = FakeNet()
    got = by_name(judged(tmp_path, [pin("fromimage", None, role="image"), pin("fromproject", None, role="dev")], net))
    assert "whatever is newest when the image is built" in got["fromimage"].note
    assert "not installed in this environment" in got["fromproject"].note


def test_one_name_is_asked_about_once_however_many_times_it_is_pinned(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])})
    deps = [
        pin("a", "1.0", source="one/Dockerfile:1"),
        pin("a", "1.0", source="two/Dockerfile:1"),
        pin("a", "1.0", source="three/Dockerfile:1"),
    ]
    report = judged(tmp_path, deps, net)
    assert len(report.findings) == 3
    assert len([c for c in net.calls if "pypi.org" in c]) == 1


# ---------- policy ----------
def test_an_accepted_advisory_and_a_held_package_are_taken_at_their_word(tmp_path):
    net = FakeNet(
        pypi={"a": ("1.0", []), "b": ("2.0", [])},
        osv={("a", "1.0"): ["GHSA-1"]},
        details={"GHSA-1": advisory_detail("bad", aliases=["CVE-9"])},
    )
    policy = Policy(
        (
            PolicyEntry(IGNORE, "CVE-9", "not reachable from our code", LATER),  # matched through the alias, as the report prints it
            PolicyEntry(HOLD, "B", "needs a rebuild first", LATER),
        )
    )
    report = judged(tmp_path, [pin("a", "1.0"), pin("b", "1.0")], net, policy)
    got = by_name(report)

    assert got["a"].status == "current"
    assert got["b"].status == "held"
    assert got["b"].note == "held back on purpose: needs a rebuild first"
    assert report.policy_problems == ()
    assert report.failed is False


def test_a_policy_entry_that_ran_out_stops_working_and_fails_the_report(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", []), "b": ("2.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")})
    policy = Policy((PolicyEntry(IGNORE, "GHSA-1", "not reachable", EARLIER), PolicyEntry(HOLD, "b", "rebuild", EARLIER)))
    report = judged(tmp_path, [pin("a", "1.0"), pin("b", "1.0")], net, policy)
    got = by_name(report)

    assert got["a"].status == "vulnerable", "an expired entry must stop suppressing the advisory"
    assert got["b"].status == "outdated"
    assert len(report.policy_problems) == 2
    assert report.failed is True


def test_an_unusable_policy_entry_fails_the_report_on_its_own(tmp_path):
    policy = Policy((PolicyEntry(IGNORE, "GHSA-1", reason="", until=LATER),))
    report = judged(tmp_path, [], FakeNet(), policy)
    assert report.policy_problems and report.failed is True


# ---------- not knowing, honestly ----------
def test_when_nothing_can_be_reached_the_report_says_so_instead_of_guessing(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])})
    net.offline = True
    report = judged(tmp_path, [pin("a", "1.0")], net)

    assert report.offline is not None and "no route" in report.offline
    assert report.failed is False, "being unable to check is not the same as finding something"
    assert by_name(report)["a"].status == "unknown"


def test_one_rate_limited_answer_is_unknown_and_the_rest_of_the_run_still_counts(tmp_path):
    net = FakeNet(pypi={"a": ("2.0", [])}, github={"o/r": "v2"})
    net.limited = {"api.github.com"}
    report = judged(tmp_path, [pin("a", "1.0"), Dep("GitHub", "o/r", "1", "Dockerfile:1")], net)
    got = by_name(report)

    assert report.offline is None
    assert got["a"].status == "outdated"
    assert got["o/r"].status == "unknown" and "rate limited" in got["o/r"].note


def test_advisories_being_rate_limited_never_turns_a_package_into_current(tmp_path):
    net = FakeNet(pypi={"a": ("2.0", [])})
    net.limited = {"api.osv.dev"}
    got = by_name(judged(tmp_path, [pin("a", "1.0")], net))
    assert got["a"].status == "outdated", "unknown advisories must not be reported as none"


def test_advisories_going_offline_makes_the_whole_run_incomplete(tmp_path):
    def half_up(url, body=None):
        if "osv.dev" in url:
            raise OfflineError("no route to host")
        return {"info": {"version": "2.0"}, "releases": {}}

    report = judged(tmp_path, [pin("a", "1.0")], half_up)
    assert report.offline is not None, "names resolved but advisories could not be had: the run knows too little to pass"


def test_an_ecosystem_with_no_client_is_unknown_and_says_why(tmp_path):
    report = judged(tmp_path, [Dep("Hackage", "aeson", "2.2.0", "project.cabal")], FakeNet())
    assert by_name(report)["aeson"].note == "no registry client for Hackage"


def test_an_empty_project_is_reported_as_empty_and_not_as_offline(tmp_path):
    report = judged(tmp_path, [], FakeNet())
    assert report.findings == () and report.offline is None and report.failed is False


# ---------- what else the report carries ----------
def test_unread_manifests_are_carried_through_to_the_report(tmp_path):
    report = judged(tmp_path, [], FakeNet(), unread=Unread(("go.mod",)))
    assert report.unread_manifests == ("go.mod",)


def test_the_counts_cover_every_status_even_at_zero_so_two_runs_can_be_compared(tmp_path):
    net = FakeNet(pypi={"a": ("2.0", [])})
    counts = judged(tmp_path, [pin("a", "1.0")], net).counts
    assert counts["outdated"] == 1
    assert counts["vulnerable"] == 0 and counts["yanked"] == 0 and counts["current"] == 0


# ---------- a release that is both withdrawn and vulnerable ----------
def test_a_withdrawn_release_with_an_advisory_is_still_recorded_as_withdrawn(tmp_path):
    """The status went to `vulnerable` and nothing else kept the withdrawal, so the headline said "0 withdrawn" about a project with one.

    `vulnerable` stays the status, because an advisory with a fixed version is the more actionable of the two. The fact is kept beside it.
    """
    net = FakeNet(pypi={"a": ("2.0", ["1.0"])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")})
    report = evaluate([pin("a", "1.0")], registries(tmp_path, net), today=TODAY)
    (finding,) = report.findings
    assert finding.status == "vulnerable"
    assert finding.withdrawn is True
    assert "also withdrawn by its author" in finding.note
    assert report.withdrawn_count == 1
    assert report.counts["yanked"] == 0, "the status count is unchanged; it is simply not the number of withdrawals"


def test_a_withdrawn_release_with_no_advisory_is_unchanged(tmp_path):
    net = FakeNet(pypi={"a": ("2.0", ["1.0"])})
    report = evaluate([pin("a", "1.0")], registries(tmp_path, net), today=TODAY)
    (finding,) = report.findings
    assert (finding.status, finding.withdrawn) == ("yanked", True)
    assert report.withdrawn_count == 1


def test_a_release_that_is_neither_is_not_marked(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])})
    report = evaluate([pin("a", "1.0")], registries(tmp_path, net), today=TODAY)
    assert report.findings[0].withdrawn is False
    assert report.withdrawn_count == 0
