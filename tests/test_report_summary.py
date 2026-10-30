"""The one-line report.

It goes in a status bar or a CI step name, so the verdict has to come first: that is the part that survives being truncated.
"""

from stocktake.evaluate import evaluate
from stocktake.models import Report
from stocktake.report import render_summary

from helpers import TODAY, FakeNet, advisory_detail, pin, registries


def judged(tmp_path, deps, net, **kwargs):
    return evaluate(deps, registries(tmp_path, net), today=TODAY, **kwargs)


def test_nothing_unsafe_says_so_first_and_still_counts_what_is_old(tmp_path):
    net = FakeNet(pypi={"a": ("2.0", []), "b": ("1.0", [])})
    line = render_summary(judged(tmp_path, [pin("a", "1.0"), pin("b", "1.0")], net))
    assert line == "stocktake: nothing unsafe, 1 outdated (2 checked)"


def test_something_vulnerable_leads_with_that(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")})
    assert render_summary(judged(tmp_path, [pin("a", "1.0")], net)) == "stocktake: 1 vulnerable (1 checked)"


def test_a_withdrawn_release_is_named_separately(tmp_path):
    net = FakeNet(pypi={"a": ("2.0", ["1.0"])})
    assert render_summary(judged(tmp_path, [pin("a", "1.0")], net)) == "stocktake: 1 withdrawn (1 checked)"


def test_an_overdue_policy_entry_is_a_failure_worth_a_line_of_its_own():
    report = Report(findings=(), policy_problems=("hold_back: a is due for a decision again",), today=TODAY.isoformat())
    assert render_summary(report) == "stocktake: 1 policy entry overdue (0 checked)"


def test_several_overdue_entries_read_correctly():
    report = Report(findings=(), policy_problems=("one", "two"), today=TODAY.isoformat())
    assert "2 policy entries overdue" in render_summary(report)


def test_every_kind_of_failure_appears_together(tmp_path):
    net = FakeNet(
        pypi={"a": ("1.0", []), "b": ("2.0", ["1.0"])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")}
    )
    report = judged(tmp_path, [pin("a", "1.0"), pin("b", "1.0")], net)
    assert render_summary(report) == "stocktake: 1 vulnerable, 1 withdrawn (2 checked)"


def test_being_unable_to_check_is_not_reported_as_a_clean_result(tmp_path):
    net = FakeNet()
    net.offline = True
    line = render_summary(judged(tmp_path, [pin("a", "1.0")], net))
    assert line.startswith("stocktake: could not check")
    assert "no route to host" in line
    assert "unsafe" not in line


def test_finding_nothing_at_all_says_that_rather_than_claiming_success(tmp_path):
    assert render_summary(judged(tmp_path, [], FakeNet())) == "stocktake: nothing found to check"


def test_the_line_is_one_line_of_plain_ascii(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")})
    for report in (judged(tmp_path, [pin("a", "1.0")], net), judged(tmp_path, [], FakeNet())):
        line = render_summary(report)
        assert "\n" not in line
        assert line.isascii()
