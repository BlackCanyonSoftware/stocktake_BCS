"""Policy: the decisions already made, and the expiry that stops them from becoming permanent.

The expiry is the load-bearing part. Without it, "ignore this for now" is indistinguishable from "ignore this forever", and the escape hatch
stops being safe to offer.
"""

from datetime import date

from stocktake.policy import HOLD, IGNORE, Policy, PolicyEntry, policy_from_toml

TODAY = date(2026, 10, 29)
LATER = date(2026, 12, 1)
EARLIER = date(2026, 10, 1)


def entry(kind=IGNORE, what="GHSA-1", reason="assessed, not reachable", until=LATER):
    return PolicyEntry(kind=kind, what=what, reason=reason, until=until)


def test_an_entry_in_date_suppresses_what_it_covers():
    policy = Policy((entry(), entry(HOLD, "pillow", "rebuild the samples first")))
    assert policy.ignored_advisories(TODAY) == {"GHSA-1"}
    assert policy.held_packages(TODAY) == {"pillow"}
    assert policy.problems(TODAY) == ()


def test_an_entry_past_its_date_suppresses_nothing_and_becomes_a_problem():
    policy = Policy((entry(until=EARLIER), entry(HOLD, "pillow", "r", EARLIER)))
    assert policy.ignored_advisories(TODAY) == frozenset()
    assert policy.held_packages(TODAY) == frozenset()
    problems = policy.problems(TODAY)
    assert len(problems) == 2
    assert all("due for a decision again" in p for p in problems)
    assert "2026-10-01" in problems[0]


def test_the_last_day_still_counts_as_in_date():
    assert Policy((entry(until=TODAY),)).ignored_advisories(TODAY) == {"GHSA-1"}


def test_an_entry_with_no_reason_or_no_usable_date_is_itself_a_problem():
    policy = Policy((PolicyEntry(IGNORE, "GHSA-1", reason="", until=LATER), PolicyEntry(HOLD, "x", reason="r", until=None)))
    problems = policy.problems(TODAY)
    assert len(problems) == 2
    assert all("needs a reason and an `until` date" in p for p in problems)


def test_an_incomplete_entry_suppresses_nothing_either():
    assert Policy((PolicyEntry(IGNORE, "GHSA-1", reason="", until=LATER),)).ignored_advisories(TODAY) == frozenset()


def test_a_held_package_is_matched_however_its_name_is_punctuated():
    policy = Policy((entry(HOLD, "Typing_Extensions", "r"),))
    assert policy.held_packages(TODAY) == {"typing-extensions"}


def test_the_reason_a_package_is_held_is_available_for_the_report():
    policy = Policy((entry(HOLD, "pillow", "12.4 changes the PNG writer"),))
    assert policy.hold_reason("Pillow", TODAY) == "12.4 changes the PNG writer"
    assert policy.hold_reason("numpy", TODAY) == ""


def test_an_expired_hold_gives_no_reason_because_it_is_no_longer_holding_anything():
    assert Policy((entry(HOLD, "pillow", "r", EARLIER),)).hold_reason("pillow", TODAY) == ""


# ---------- reading it out of a config table ----------
def test_a_toml_table_becomes_entries_with_native_dates():
    policy = policy_from_toml(
        {
            "ignore_advisories": [{"id": "GHSA-1", "reason": "assessed", "until": LATER}],
            "hold_back": [{"package": "pillow", "reason": "rebuild first", "until": "2026-12-01"}],
        }
    )
    assert [(e.kind, e.what, e.until) for e in policy.entries] == [(IGNORE, "GHSA-1", LATER), (HOLD, "pillow", LATER)]


def test_a_date_written_as_an_unparseable_string_becomes_no_date_rather_than_an_error():
    policy = policy_from_toml({"hold_back": [{"package": "x", "reason": "r", "until": "soon"}]})
    assert policy.entries[0].until is None
    assert "needs a reason and an `until` date" in policy.problems(TODAY)[0]


def test_an_entry_missing_everything_is_still_kept_so_it_can_be_reported():
    policy = policy_from_toml({"ignore_advisories": [{}]})
    assert policy.entries[0].what == "?"
    assert policy.problems(TODAY)


def test_an_empty_or_absent_table_is_an_empty_policy():
    assert policy_from_toml({}).entries == ()
    assert policy_from_toml({"ignore_advisories": [], "hold_back": None}).entries == ()


def test_something_that_is_not_a_table_in_the_list_is_skipped():
    assert policy_from_toml({"hold_back": ["pillow"]}).entries == ()
