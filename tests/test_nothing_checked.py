"""A run that checked nothing, and the one-call helper for a project driving StockTake by hand.

Both came out of the Windows README-first trial, which found no P0s and then built the fixture nobody had thought to build: a Go project,
whose every dependency file is a kind StockTake has no reader for. It reported `0 checked`, named both files, and exited 0 — a permanently
green CI gate over a project nobody had looked at ([ADR 0010](../docs/adr/0010-a-run-that-checked-nothing-is-not-a-pass.md)).
"""

import json

import pytest

from stocktake.check import assert_safe, failure_text, incomplete_text, problems, run_check
from stocktake.cli import INCOMPLETE, OK, UNSAFE, run
from stocktake.report import render_json, render_sarif, render_summary, render_text

from helpers import TODAY, FakeNet, advisory_detail, registries


def go_project(tmp_path, config: str = ""):
    """A project whose only dependency files are kinds nothing reads yet."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "go.mod").write_text("module example.com/x\n\ngo 1.22\n", encoding="utf-8")
    (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    if config:
        (root / ".stocktake.toml").write_text(config, encoding="utf-8")
    return root


def judged(tmp_path, root, net=None, **kwargs):
    return run_check(root, registries=registries(tmp_path, net or FakeNet()), installed=lambda name: None, today=TODAY, **kwargs)


# ---------- the rule ----------
def test_a_project_whose_every_manifest_is_unread_is_not_a_checked_project(tmp_path):
    report = judged(tmp_path, go_project(tmp_path))
    assert report.findings == ()
    assert report.unread_manifests == ("go.mod", "pnpm-lock.yaml")
    assert report.nothing_was_checked
    assert not report.complete
    assert not report.failed, "nothing unsafe was found; the point is that nothing was looked at"


def test_partial_coverage_is_still_a_pass(tmp_path):
    """200 of 201 checked is a report with a named gap. 0 of 1 is not a report. Only the second one fails.

    This is the whole boundary, and it is a judgement rather than a principle, so it gets the test that states it.
    """
    root = go_project(tmp_path)
    (root / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    report = judged(tmp_path, root, FakeNet(pypi={"flask": ("3.0.0", [])}))
    assert [f.dep.name for f in report.findings] == ["flask"]
    assert report.unread_manifests == ("go.mod", "pnpm-lock.yaml")
    assert not report.nothing_was_checked
    assert report.complete


def test_a_project_with_no_dependency_files_at_all_is_still_a_pass(tmp_path):
    """There is nothing to point at, and a project with genuinely no dependencies has nothing unsafe in it."""
    root = tmp_path / "empty"
    root.mkdir()
    (root / "README.md").write_text("nothing here\n", encoding="utf-8")
    report = judged(tmp_path, root)
    assert not report.nothing_was_checked
    assert report.complete


def test_accepting_the_unread_files_restores_the_pass(tmp_path):
    """The escape hatch, and the sentence it makes the project write: these are the files, and I know they are not checked."""
    root = go_project(tmp_path, 'accept_unread = ["go.mod", "pnpm-lock.yaml"]\n')
    report = judged(tmp_path, root)
    assert report.accepted_unread == ("go.mod", "pnpm-lock.yaml")
    assert report.unread_manifests == ()
    assert report.complete


def test_excluding_the_only_manifest_is_a_deliberate_statement_and_still_passes(tmp_path):
    root = go_project(tmp_path, 'exclude = ["go.mod", "pnpm-lock.yaml"]\n')
    assert judged(tmp_path, root).complete


# ---------- what it says ----------
def test_every_format_says_the_project_was_not_checked(tmp_path):
    report = judged(tmp_path, go_project(tmp_path))

    text = render_text(report)
    assert "Nothing was checked" in text
    assert "accept_unread" in text, "an exit code nobody can satisfy is one people route around"

    assert render_summary(report) == "stocktake: nothing checked, 2 dependency files have no reader yet"

    data = json.loads(render_json(report))
    assert data["complete"] is False
    assert data["failed"] is False, "a gate reading `failed` alone cannot tell this from a clean project"

    log = json.loads(render_sarif(report))
    assert log["runs"][0]["invocations"][0]["executionSuccessful"] is False


def test_the_message_names_the_files_and_the_way_out(tmp_path):
    message = incomplete_text(judged(tmp_path, go_project(tmp_path)))
    assert message is not None
    assert "go.mod, pnpm-lock.yaml" in message
    assert "accept_unread" in message


def test_the_command_exits_two(tmp_path):
    printed: list[str] = []
    code = run(
        ["--root", str(go_project(tmp_path))],
        registries=registries(tmp_path, FakeNet()),
        out=printed.append,
        installed=lambda name: None,
        today=TODAY,
    )
    assert code == INCOMPLETE
    assert code not in (OK, UNSAFE)


def test_the_command_exits_zero_once_the_project_accepts_them(tmp_path):
    root = go_project(tmp_path, 'accept_unread = ["go.mod", "pnpm-lock.yaml"]\n')
    code = run(
        ["--root", str(root)],
        registries=registries(tmp_path, FakeNet()),
        out=lambda _text: None,
        installed=lambda name: None,
        today=TODAY,
    )
    assert code == OK


# ---------- the first line of a failure ----------
def test_a_failure_says_what_happened_on_its_first_line(tmp_path):
    """pytest prints the first line of an assertion message after the dash in its one-line summary.

    This used to begin with a blank line, so every failing run showed `FAILED stocktake_dependency_check - ` and nothing after it.
    """
    net = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")})
    root = tmp_path / "p"
    root.mkdir()
    (root / "requirements.txt").write_text("a==1.0\n", encoding="utf-8")
    text = failure_text(judged(tmp_path, root, net))
    assert text is not None
    assert text.splitlines()[0] == "StockTake found 1 vulnerable."


def test_an_overdue_policy_entry_is_named_on_that_line_too(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    (root / ".stocktake.toml").write_text(
        '[[policy.hold_back]]\npackage = "flask"\nreason = "later"\nuntil = 2026-01-01\n',
        encoding="utf-8",
    )
    text = failure_text(judged(tmp_path, root, FakeNet(pypi={"flask": ("3.0.0", [])})))
    assert text is not None
    assert text.splitlines()[0] == "StockTake found 1 policy entry overdue."


# ---------- the one-call helper ----------
def test_assert_safe_raises_carrying_the_whole_report(tmp_path):
    """`assert failure_text(report) is None` passes the text to nobody: a bare AssertionError, and not one word about the package.

    The README printed that line, and a trial run wrote it down and hit exactly that. This is what it is replaced with.
    """
    net = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("very bad")})
    root = tmp_path / "p"
    root.mkdir()
    (root / "requirements.txt").write_text("a==1.0\n", encoding="utf-8")

    with pytest.raises(AssertionError) as caught:
        assert_safe(root, registries=registries(tmp_path, net), installed=lambda name: None, today=TODAY)

    message = str(caught.value)
    assert message.splitlines()[0] == "StockTake found 1 vulnerable."
    assert "a 1.0" in message and "GHSA-1" in message and "very bad" in message


def test_assert_safe_returns_the_report_when_there_is_nothing_wrong(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    report = assert_safe(
        root, registries=registries(tmp_path, FakeNet(pypi={"flask": ("3.0.0", [])})), installed=lambda n: None, today=TODAY
    )
    assert [f.status for f in report.findings] == ["current"]


def test_assert_safe_also_raises_on_a_project_it_could_not_check(tmp_path):
    """The reason to have one call rather than two: a caller who remembered the unsafe case would not have remembered this one."""
    with pytest.raises(AssertionError, match="checked nothing in this project"):
        assert_safe(go_project(tmp_path), registries=registries(tmp_path, FakeNet()), installed=lambda name: None, today=TODAY)


def test_problems_puts_the_caveat_before_the_findings(tmp_path):
    """When a run is both partial and unsafe, what the reader needs first is how much of the rest to trust."""
    net = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")})
    root = tmp_path / "p"
    root.mkdir()
    (root / "requirements.txt").write_text("a==1.0\n", encoding="utf-8")
    (root / "package.json").write_text("{broken", encoding="utf-8")

    message = problems(judged(tmp_path, root, net))
    assert message is not None
    assert message.index("could not read") < message.index("StockTake found 1 vulnerable.")


def test_problems_is_none_for_a_clean_complete_run(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    assert problems(judged(tmp_path, root, FakeNet(pypi={"flask": ("3.0.0", [])}))) is None
