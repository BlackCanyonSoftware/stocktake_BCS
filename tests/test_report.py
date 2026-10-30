"""The report itself: what is shown first, what is collapsed, and what a program gets.

The layout is the design (docs/DESIGN.md), so it is asserted rather than left to drift.
"""

import json

from stocktake.evaluate import evaluate
from stocktake.models import Dep, Report, Unread
from stocktake.report import as_dict, render_json, render_text

from helpers import TODAY, FakeNet, advisory_detail, pin, registries


def judged(tmp_path, deps, net, unread=None):
    return evaluate(deps, registries(tmp_path, net), None, TODAY, unread)


def sample(tmp_path, unread=None):
    net = FakeNet(
        pypi={"requests": ("2.40.0", []), "pillow": ("12.4.0", []), "numpy": ("2.5.3", [])},
        osv={("requests", "2.34.2"): ["GHSA-aaaa"]},
        details={"GHSA-aaaa": advisory_detail("Header injection", fixed=["2.35.0"], package="requests")},
    )
    deps = [pin("pillow", "12.3.0"), pin("requests", "2.34.2"), pin("numpy", "2.5.3"), pin("pytest", None)]
    return judged(tmp_path, deps, net, unread)


# ---------- text ----------
def test_what_must_be_fixed_comes_first_and_what_is_fine_collapses_to_a_count(tmp_path):
    text = render_text(sample(tmp_path))
    assert text.index("VULNERABLE (fix these)") < text.index("OUTDATED") < text.index("UNPINNED") < text.index("CURRENT: 1 up to date")
    assert "numpy" not in text.split("CURRENT")[0], "a package with nothing wrong with it is counted, not listed"


def test_a_vulnerable_row_names_the_advisory_and_the_version_that_clears_it(tmp_path):
    text = render_text(sample(tmp_path))
    assert "requests 2.34.2  1 advisory (1 unrated); upgrade to 2.35.0 or newer" in text
    assert "GHSA-aaaa unrated: Header injection" in text


def test_an_outdated_row_names_the_jump_and_how_big_it_is(tmp_path):
    assert "pillow 12.3.0 -> 12.4.0 (minor)" in render_text(sample(tmp_path))


def test_the_headline_counts_what_was_found(tmp_path):
    first_line = render_text(sample(tmp_path)).splitlines()[0]
    assert first_line == f"Dependency check {TODAY.isoformat()}: 4 checked, 1 vulnerable, 0 withdrawn, 1 outdated, 1 unpinned"


def test_the_report_can_be_narrowed_to_what_needs_action(tmp_path):
    report = sample(tmp_path)
    only_unsafe = render_text(report, "vulnerable")
    assert "VULNERABLE" in only_unsafe and "OUTDATED" not in only_unsafe and "UNPINNED" not in only_unsafe

    old_or_worse = render_text(report, "outdated")
    assert "VULNERABLE" in old_or_worse and "OUTDATED" in old_or_worse and "UNPINNED" not in old_or_worse


def test_every_row_leads_with_where_it_came_from(tmp_path):
    net = FakeNet(pypi={"a": ("2.0", [])})
    report = judged(tmp_path, [pin("a", "1.0", source="docker/dev/Dockerfile:12")], net)
    row = next(line for line in render_text(report).splitlines() if "a 1.0" in line)
    assert row.strip().startswith("docker/dev/Dockerfile:12")


def test_rows_are_ordered_by_where_they_came_from_so_two_runs_read_the_same(tmp_path):
    net = FakeNet(pypi={"a": ("2.0", []), "b": ("2.0", [])})
    deps = [pin("b", "1.0", source="z/Dockerfile:1"), pin("a", "1.0", source="a/Dockerfile:1")]
    lines = [line for line in render_text(judged(tmp_path, deps, net)).splitlines() if "Dockerfile" in line]
    assert lines[0].strip().startswith("a/Dockerfile:1")


def test_a_package_with_many_advisories_is_summarised_worst_first_with_the_rest_counted(tmp_path):
    # The real case this exists for: ninety entries for one pinned version. Printing all of them is the same as printing none.
    ids = [f"GHSA-{i:04d}" for i in range(12)]
    net = FakeNet(
        pypi={"big": ("2.0", [])},
        osv={("big", "1.0"): ids},
        details={
            i: advisory_detail(f"problem {n}", "CRITICAL" if n == 11 else "MODERATE", fixed=["2.0"], package="big")
            for n, i in enumerate(ids)
        },
    )
    report = judged(tmp_path, [pin("big", "1.0")], net)
    text = render_text(report)

    assert "big 1.0  12 advisories (1 critical, 11 moderate); upgrade to 2.0 or newer" in text
    assert text.index("GHSA-0011 CRITICAL") < text.index("GHSA-0000 MODERATE"), "the worst one has to be visible"
    assert "... and 7 more (stocktake --only vulnerable --all-advisories)" in text, "and the way to see the rest has to be in the report"
    assert text.count("GHSA-") == 5
    assert render_text(report, all_advisories=True).count("GHSA-") == 12


def test_an_advisory_with_no_named_fix_says_so_rather_than_guessing(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("no fix yet")})
    assert "no fixed version named" in render_text(judged(tmp_path, [pin("a", "1.0")], net))


def test_a_policy_problem_is_shown_above_everything_else():
    report = Report(findings=(), policy_problems=("hold_back: a is due for a decision again",), today="2026-10-29")
    text = render_text(report)
    assert "POLICY: hold_back: a is due for a decision again" in text


def test_being_offline_is_stated_in_the_headline_and_nothing_is_called_clean(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])})
    net.offline = True
    text = render_text(judged(tmp_path, [pin("a", "1.0")], net))
    assert "[offline: no route to host]" in text.splitlines()[0]
    assert "CURRENT" not in text


def test_an_unread_manifest_is_named_in_the_report(tmp_path):
    text = render_text(sample(tmp_path, unread=Unread(("go.mod",))))
    assert "UNREAD" in text and "go.mod" in text


def test_finding_nothing_at_all_is_stated_because_silence_looks_like_success(tmp_path):
    text = render_text(judged(tmp_path, [], FakeNet()))
    assert "Nothing was found to check" in text


def test_the_report_is_plain_ascii_with_no_colour_or_box_drawing(tmp_path):
    text = render_text(sample(tmp_path, unread=Unread(("go.mod",))))
    assert text.isascii()
    assert "\x1b" not in text, "no escape codes: this text lands in pytest summaries and CI logs"


# ---------- json ----------
def test_the_json_report_carries_everything_a_program_needs(tmp_path):
    data = json.loads(render_json(sample(tmp_path)))
    assert data["failed"] is True
    assert data["offline"] is None
    assert data["counts"]["outdated"] == 1

    row = next(f for f in data["findings"] if f["name"] == "requests")
    assert row["status"] == "vulnerable"
    assert row["source"] == "docker/dev/Dockerfile:1"
    assert row["advisories"][0]["fixed"] == ["2.35.0"]
    assert row["fix_target"] == "2.35.0", "the upgrade target is computed here so a caller cannot get the backport rule wrong"


def test_a_finding_with_nothing_against_it_has_no_fix_target(tmp_path):
    data = as_dict(sample(tmp_path))
    assert next(f for f in data["findings"] if f["name"] == "pillow")["fix_target"] is None


def test_the_json_report_includes_the_dependency_as_declared(tmp_path):
    net = FakeNet(pypi={"a": ("2.0", [])})
    report = judged(tmp_path, [Dep("PyPI", "a", "1.0", "pyproject.toml", ">=1", "dev")], net)
    row = as_dict(report)["findings"][0]
    assert (row["ecosystem"], row["spec"], row["role"]) == ("PyPI", ">=1", "dev")


def test_the_json_report_is_valid_json_even_when_offline(tmp_path):
    net = FakeNet()
    net.offline = True
    data = json.loads(render_json(judged(tmp_path, [pin("a", "1.0")], net)))
    assert data["offline"] and data["failed"] is False
