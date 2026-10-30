"""Merging advisories into one entry per real problem, and working out the single version that clears them all.

This is the code that turns ninety OSV entries for one package into something a person acts on, so it is tested on its own.
"""

from stocktake.advisories import fix_target, merge_advisories, severity_tally
from stocktake.models import Advisory


def adv(id_, severity="HIGH", aliases=(), fixed=(), summary="s"):
    return Advisory(id=id_, severity=severity, summary=summary, aliases=tuple(aliases), fixed=tuple(fixed))


def test_a_ghsa_and_its_pysec_twin_are_one_problem_with_the_worst_severity_and_every_fix():
    merged = merge_advisories(
        [
            adv("PYSEC-1", "", ["CVE-1", "GHSA-1"], ["2.0"], "twin"),
            adv("GHSA-1", "CRITICAL", ["CVE-1"], ["2.0", "1.9.5"], "the real one"),
            adv("GHSA-2", "LOW", [], ["3.0"]),
            adv("PYSEC-2", "", ["GHSA-2"], []),
        ]
    )
    assert [(a.id, a.severity) for a in merged] == [("GHSA-1", "CRITICAL"), ("GHSA-2", "LOW")]
    assert merged[0].fixed == ("1.9.5", "2.0")
    assert set(merged[0].aliases) == {"CVE-1", "PYSEC-1"}
    assert merged[0].summary == "the real one"


def test_advisories_chained_through_shared_aliases_all_land_in_one_group():
    # A and B share CVE-1; B and C share CVE-2. All three are the same problem.
    merged = merge_advisories([adv("A", aliases=["CVE-1"]), adv("B", aliases=["CVE-1", "CVE-2"]), adv("C", aliases=["CVE-2"])])
    assert len(merged) == 1
    assert set(merged[0].aliases) >= {"CVE-1", "CVE-2"}


def test_an_unrated_advisory_sorts_last_but_is_not_treated_as_low():
    merged = merge_advisories([adv("GHSA-unrated", ""), adv("GHSA-low", "LOW")])
    assert [a.id for a in merged] == ["GHSA-low", "GHSA-unrated"]
    assert merged[1].label == "unrated"


def test_the_fix_target_is_the_version_that_clears_every_advisory():
    advisories = [adv("A", fixed=["1.9.5", "2.1"]), adv("B", fixed=["2.4"]), adv("C", fixed=[])]
    assert fix_target(advisories, "1.9.0") == "2.4"


def test_a_fix_backported_to_a_branch_we_are_not_on_is_not_a_fix_for_us():
    assert fix_target([adv("A", fixed=["1.9.5", "2.1"])], "2.0") == "2.1"


def test_an_advisory_naming_no_fix_gives_no_target_rather_than_a_guess():
    assert fix_target([adv("A")], "1.0") is None


def test_the_severity_tally_counts_worst_first_and_in_the_words_the_report_prints():
    tally = severity_tally([adv("a", "MODERATE"), adv("b", "CRITICAL"), adv("c", "MODERATE"), adv("d", "")])
    assert tally == [("critical", 1), ("moderate", 2), ("unrated", 1)]
