"""`ignore_package`: a vulnerable package accepted in one entry, with a reason and a date.

Added because the narrow form does not scale. A trial against a real project put the cost plainly: accepting `electron`'s 46 advisories and
`tar`'s 12 would have meant 58 `ignore_advisories` entries, so the practical outcome is that nobody gates on the check at all — which is a
worse place to be than a policy entry somebody has to renew ([ADR 0011](../docs/adr/0011-accepting-a-vulnerable-package.md)).

The tests here are mostly about what an acceptance must *not* do: hide the advisories, survive a version change, survive its own expiry, or
disappear from a narrowed report.
"""

import json

import pytest

from stocktake.check import problems, run_check
from stocktake.cli import INCOMPLETE, OK, UNSAFE, run
from stocktake.config import ConfigError, load_config
from stocktake.evaluate import evaluate
from stocktake.policy import ACCEPT, Policy, PolicyEntry
from stocktake.report import render_json, render_sarif, render_summary, render_text

from helpers import TODAY, FakeNet, advisory_detail, pin, registries

LATER = TODAY.replace(year=TODAY.year + 1)
EARLIER = TODAY.replace(year=TODAY.year - 1)


def accepting(package: str, version: str = "", until=LATER, reason: str = "not reachable in our use") -> Policy:
    return Policy((PolicyEntry(kind=ACCEPT, what=package, reason=reason, until=until, version=version),))


def vulnerable_net(name: str = "electron", version: str = "33.4.11", ids=("GHSA-1", "GHSA-2")):
    return FakeNet(
        pypi={name: ("42.0.0", [])},
        osv={(name, version): list(ids)},
        details={i: advisory_detail(f"problem {i}", "HIGH", fixed=("42.0.0",)) for i in ids},
    )


def judged(tmp_path, policy=None, name="electron", version="33.4.11"):
    return evaluate([pin(name, version)], registries(tmp_path, vulnerable_net(name, version)), policy, TODAY)


# ---------- the decision ----------
def test_accepting_a_package_stops_it_failing_the_build(tmp_path):
    report = judged(tmp_path, accepting("electron", "33.4.11"))
    (finding,) = report.findings
    assert finding.status == "accepted"
    assert finding.severity == "info"
    assert not report.failed


def test_the_advisories_are_kept_rather_than_dropped(tmp_path):
    """An acceptance is a decision to carry a known risk. A report that stopped showing the risk would make the decision unreviewable, which
    is the whole argument for requiring a date on it."""
    (finding,) = judged(tmp_path, accepting("electron", "33.4.11")).findings
    assert [a.id for a in finding.advisories] == ["GHSA-1", "GHSA-2"]
    assert "2 known advisories" in finding.note


def test_the_note_says_who_decided_what_and_until_when(tmp_path):
    (finding,) = judged(tmp_path, accepting("electron", "33.4.11", reason="shipping behind a kiosk, no browser surface")).findings
    assert f"accepted on purpose until {LATER}" in finding.note
    assert "shipping behind a kiosk, no browser surface" in finding.note


def test_without_the_entry_it_fails_as_before(tmp_path):
    report = judged(tmp_path)
    assert [f.status for f in report.findings] == ["vulnerable"]
    assert report.failed


# ---------- what it must not do ----------
def test_an_acceptance_does_not_carry_forward_to_another_version(tmp_path):
    """`electron 33.4.11` being accepted says nothing about `electron 34`. An acceptance that silently followed the package to a version
    nobody had looked at would be the one failure a policy file must not have."""
    report = evaluate(
        [pin("electron", "34.0.0")],
        registries(tmp_path, vulnerable_net("electron", "34.0.0")),
        accepting("electron", "33.4.11"),
        TODAY,
    )
    assert [f.status for f in report.findings] == ["vulnerable"]
    assert report.failed


def test_an_entry_with_no_version_covers_every_version_because_it_said_so(tmp_path):
    """The broader statement, available but never inferred: leaving the version out is a deliberate act in the config file."""
    report = evaluate(
        [pin("electron", "34.0.0")],
        registries(tmp_path, vulnerable_net("electron", "34.0.0")),
        accepting("electron"),
        TODAY,
    )
    assert [f.status for f in report.findings] == ["accepted"]


def test_an_expired_acceptance_stops_suppressing_and_fails_the_run(tmp_path):
    """Both halves matter. It goes back to failing on its own merits, and the overdue entry is named as a policy problem."""
    report = judged(tmp_path, accepting("electron", "33.4.11", until=EARLIER))
    assert [f.status for f in report.findings] == ["vulnerable"]
    assert report.failed
    assert any("electron 33.4.11" in problem and "due for a decision again" in problem for problem in report.policy_problems)


def test_an_entry_with_no_reason_or_no_date_is_a_problem_rather_than_a_suppression(tmp_path):
    policy = Policy((PolicyEntry(kind=ACCEPT, what="electron", version="33.4.11", reason="", until=None),))
    report = judged(tmp_path, policy)
    assert [f.status for f in report.findings] == ["vulnerable"]
    assert any("needs a reason and an `until` date" in problem for problem in report.policy_problems)


def test_the_overdue_message_names_the_version_that_was_accepted(tmp_path):
    policy = accepting("electron", "33.4.11", until=EARLIER)
    assert policy.problems(TODAY)[0].startswith("ignore_package: electron 33.4.11 was accepted until")


def test_a_withdrawn_release_can_be_accepted_too(tmp_path):
    """`yanked` fails for the same reason `vulnerable` does, so the same decision has to be available for it."""
    net = FakeNet(pypi={"a": ("2.0", ["1.0"])})
    report = evaluate([pin("a", "1.0")], registries(tmp_path, net), accepting("a", "1.0"), TODAY)
    (finding,) = report.findings
    assert finding.status == "accepted"
    assert finding.withdrawn is True
    assert not report.failed


def test_holding_a_package_back_still_does_not_suppress_its_vulnerability(tmp_path):
    """The distinction `ignore_package` exists to keep. `hold_back` accepts being out of date and nothing else."""
    from stocktake.policy import HOLD

    policy = Policy((PolicyEntry(kind=HOLD, what="electron", reason="later", until=LATER),))
    assert [f.status for f in judged(tmp_path, policy).findings] == ["vulnerable"]


# ---------- it stays visible ----------
def test_it_is_in_the_headline_and_its_own_section(tmp_path):
    text = render_text(judged(tmp_path, accepting("electron", "33.4.11")))
    assert "1 accepted" in text.splitlines()[0]
    assert "ACCEPTED (known, and accepted on purpose" in text
    assert "GHSA-1" in text, "the advisories being carried are listed, not summarised away"


def test_a_narrowed_report_still_shows_it(tmp_path):
    """`--only vulnerable` asks what is unsafe here, and a carried vulnerability is unsafe whether or not somebody signed for it.

    Narrowing is for hiding what needs no action, never for hiding risk.
    """
    report = judged(tmp_path, accepting("electron", "33.4.11"))
    assert "ACCEPTED" in render_text(report, "vulnerable")
    assert "ACCEPTED" in render_text(report, "outdated")


def test_the_one_line_summary_will_not_say_nothing_unsafe(tmp_path):
    line = render_summary(judged(tmp_path, accepting("electron", "33.4.11")))
    assert line == "stocktake: nothing unsafe beyond what is accepted, 0 outdated, 1 accepted (1 checked)"


def test_the_summary_names_it_beside_a_real_failure_too(tmp_path):
    net = vulnerable_net("electron", "33.4.11")
    net.pypi["other"] = ("2.0", [])
    net.osv[("other", "1.0")] = ["GHSA-9"]
    net.details["GHSA-9"] = advisory_detail("another", "HIGH")
    report = evaluate([pin("electron", "33.4.11"), pin("other", "1.0")], registries(tmp_path, net), accepting("electron", "33.4.11"), TODAY)
    assert render_summary(report) == "stocktake: 1 vulnerable, 1 accepted (2 checked)"


def test_json_gives_it_its_own_status_and_counts_it(tmp_path):
    data = json.loads(render_json(judged(tmp_path, accepting("electron", "33.4.11"))))
    assert data["counts"]["accepted"] == 1
    assert data["failed"] is False
    (finding,) = data["findings"]
    assert finding["status"] == "accepted"
    assert len(finding["advisories"]) == 2, "a machine reader can still see exactly what is being carried"


def test_sarif_reports_it_as_a_warning_so_it_stays_reviewable(tmp_path):
    """Not an error, because it fails nothing; not a note, because it is a real vulnerability somebody signed for."""
    log = json.loads(render_sarif(judged(tmp_path, accepting("electron", "33.4.11"))))
    (result,) = [r for r in log["runs"][0]["results"] if r["ruleId"] == "accepted"]
    assert result["level"] == "warning"
    assert "accepted on purpose" in result["message"]["text"]


def test_it_is_not_reported_as_something_to_fix(tmp_path):
    assert problems(judged(tmp_path, accepting("electron", "33.4.11"))) is None


# ---------- from a config file ----------
def test_it_reads_from_a_config_file(tmp_path):
    (tmp_path / ".stocktake.toml").write_text(
        "[[policy.ignore_package]]\n"
        'package = "electron"\n'
        'version = "33.4.11"\n'
        'reason = "no browser surface in a kiosk build"\n'
        f"until = {LATER.isoformat()}\n",
        encoding="utf-8",
    )
    policy = load_config(tmp_path).policy
    entry = policy.accepted_vulnerability("electron", "33.4.11", TODAY)
    assert entry is not None
    assert (entry.what, entry.version, entry.until) == ("electron", "33.4.11", LATER)
    assert policy.accepted_vulnerability("electron", "34.0.0", TODAY) is None


def test_the_package_name_is_matched_the_way_every_other_name_is(tmp_path):
    """PEP 503 normalisation, so `Left-Pad` in a config file covers `left_pad` in a manifest."""
    assert accepting("Left-Pad", "1.0.0").accepted_vulnerability("left_pad", "1.0.0", TODAY) is not None


def test_a_misspelt_policy_kind_is_refused_rather_than_silently_nothing(tmp_path):
    """`[[policy.ignore_packages]]` was read as no policy at all. It is the `excludes` bug, in the file where it matters most."""
    (tmp_path / ".stocktake.toml").write_text(
        '[[policy.ignore_packages]]\npackage = "electron"\nreason = "r"\nuntil = 2027-01-01\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match=r"unknown policy kind in `\[policy\]`: `ignore_packages`"):
        load_config(tmp_path)


# ---------- end to end ----------
def test_the_command_exits_zero_with_an_acceptance_and_one_without(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "requirements.txt").write_text("electron==33.4.11\n", encoding="utf-8")
    net = vulnerable_net("electron", "33.4.11")

    def code_for(config: str | None) -> int:
        path = root / ".stocktake.toml"
        path.write_text(config, encoding="utf-8") if config else path.unlink(missing_ok=True)
        return run(
            ["--root", str(root)],
            registries=registries(tmp_path, net),
            out=lambda _text: None,
            installed=lambda name: None,
            today=TODAY,
        )

    assert code_for(None) == UNSAFE
    accepted = (
        "[[policy.ignore_package]]\n"
        'package = "electron"\n'
        'version = "33.4.11"\n'
        'reason = "kiosk build, no browser surface"\n'
        f"until = {LATER.isoformat()}\n"
    )
    assert code_for(accepted) == OK
    expired = accepted.replace(LATER.isoformat(), EARLIER.isoformat())
    assert code_for(expired) == UNSAFE, "an expired entry fails, and the failure is the point of the date"
    assert code_for(None) == UNSAFE
    assert INCOMPLETE not in (OK, UNSAFE)


def test_one_entry_replaces_what_would_have_been_fifty_eight(tmp_path):
    """The number from the trial report, as a test: 46 advisories on one package, accepted by one entry rather than 46."""
    ids = tuple(f"GHSA-{n}" for n in range(46))
    net = vulnerable_net("electron", "33.4.11", ids)
    report = evaluate([pin("electron", "33.4.11")], registries(tmp_path, net), accepting("electron", "33.4.11"), TODAY)
    (finding,) = report.findings
    assert len(finding.advisories) == 46
    assert finding.status == "accepted"
    assert not report.failed
    assert len(accepting("electron", "33.4.11").entries) == 1


def test_run_check_reads_the_entry_from_the_projects_own_config(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "requirements.txt").write_text("electron==33.4.11\n", encoding="utf-8")
    (root / ".stocktake.toml").write_text(
        f'[[policy.ignore_package]]\npackage = "electron"\nversion = "33.4.11"\nreason = "kiosk build"\nuntil = {LATER.isoformat()}\n',
        encoding="utf-8",
    )
    report = run_check(
        root,
        registries=registries(tmp_path, vulnerable_net("electron", "33.4.11")),
        installed=lambda name: None,
        today=TODAY,
    )
    assert [f.status for f in report.findings] == ["accepted"]
    assert not report.failed
