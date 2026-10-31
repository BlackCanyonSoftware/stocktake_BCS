"""A manifest StockTake meant to read and could not.

Every case here came out of a trial run against a real project, which reported `stocktake: nothing found to check` and exit 0 for a project
whose `package.json` was truncated, whose `requirements.txt` was UTF-16, and whose other `requirements.txt` was a JPEG by mistake. Nothing in
the output said a file had been skipped. That is the one way this tool must not fail, so the whole path has a test: the walk, every format,
the exit code, and the pytest item ([ADR 0009](../docs/adr/0009-an-unread-file-makes-the-run-incomplete.md)).
"""

import codecs
import json

import pytest

from stocktake.check import incomplete_text, run_check
from stocktake.cli import INCOMPLETE, UNSAFE
from stocktake.models import Report, Unreadable
from stocktake.readers.base import UnreadableManifest, read_manifest
from stocktake.report import render_json, render_sarif, render_summary, render_text
from stocktake.scan import scan

from helpers import TODAY, FakeNet, advisory_detail, registries


def unreadable_project(tmp_path, name="requirements.txt", content=b"\xff\xfe"):
    root = tmp_path / "project"
    root.mkdir()
    (root / name).write_bytes(content)
    return root


# ---------- decoding ----------
def test_a_utf16_requirements_file_is_read_rather_than_coming_back_as_nothing(tmp_path):
    """PowerShell's `>` writes UTF-16, so this is a common accident and not an exotic one.

    Read with `errors="replace"` it came back as a NUL between every character, matched no requirement, and was reported as a project with no
    dependencies in it. The file is perfectly good; it was the reading that was wrong.
    """
    path = tmp_path / "requirements.txt"
    path.write_text("flask==3.0.0\nclick==8.1.7\n", encoding="utf-16")
    assert read_manifest(path).splitlines() == ["flask==3.0.0", "click==8.1.7"]

    found = scan(tmp_path, installed=lambda name: None)
    assert [(d.name, d.version) for d in found.deps] == [("flask", "3.0.0"), ("click", "8.1.7")]
    assert found.unreadable == []


@pytest.mark.parametrize(
    ("mark", "encoding"),
    [
        (codecs.BOM_UTF8, "utf-8"),
        (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"),
        (codecs.BOM_UTF32_LE, "utf-32-le"),
        (codecs.BOM_UTF32_BE, "utf-32-be"),
    ],
)
def test_every_byte_order_mark_a_text_editor_writes_is_understood(tmp_path, mark, encoding):
    """Python's `utf-16-le` codec writes no mark of its own, so each one is put in front of the payload here deliberately."""
    path = tmp_path / "requirements.txt"
    path.write_bytes(mark + "flask==3.0.0\n".encode(encoding))
    assert "flask==3.0.0" in read_manifest(path)


def test_a_file_that_is_not_text_at_all_is_refused_rather_than_mangled(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xfe\xfd")
    with pytest.raises(UnreadableManifest, match="is not text"):
        read_manifest(path)


def test_a_utf32_file_is_not_mistaken_for_utf16(tmp_path):
    """The UTF-32-LE mark begins with the two bytes of the UTF-16-LE mark, so the order the marks are tested in is load-bearing."""
    path = tmp_path / "requirements.txt"
    path.write_bytes(codecs.BOM_UTF32_LE + "flask==3.0.0\n".encode("utf-32-le"))
    assert "flask==3.0.0" in read_manifest(path)


def test_utf16_saved_without_a_byte_order_mark_is_refused_rather_than_read_as_nothing(tmp_path):
    """Valid UTF-8 as far as the decoder is concerned, and a NUL between every character once decoded, so no requirement matches.

    The same failure as the marked case, with no mark to notice it by, so it is caught by what the decoded text holds instead.
    """
    path = tmp_path / "requirements.txt"
    path.write_bytes("flask==3.0.0\n".encode("utf-16-le"))
    with pytest.raises(UnreadableManifest, match="NUL bytes"):
        read_manifest(path)


# ---------- the walk ----------
def test_a_manifest_that_cannot_be_read_is_carried_out_of_the_walk_not_dropped(tmp_path):
    root = unreadable_project(tmp_path, "package.json", b'{"dependencies": {"left-pad": ')
    found = scan(root, installed=lambda name: None)
    assert found.deps == []
    assert [(u.path, "JSON" in u.reason) for u in found.unreadable] == [("package.json", True)]


def test_what_a_reader_managed_to_read_before_giving_up_is_kept(tmp_path):
    """A half-read file is both things at once: the dependencies found in it are real, and the file is still reported as unreadable."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "requirements.txt").write_text("flask==3.0.0\n-r broken.in\n", encoding="utf-8")
    (root / "broken.in").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\xfd")
    found = scan(root, installed=lambda name: None)
    assert [d.name for d in found.deps] == ["flask"]
    assert [u.path for u in found.unreadable] == ["requirements.txt"]
    assert "broken.in" in found.unreadable[0].reason


def test_the_reason_names_the_file_and_what_was_wrong_with_it(tmp_path):
    root = unreadable_project(tmp_path, "pyproject.toml", b"[project\nname = ")
    (path,) = scan(root, installed=lambda name: None).unreadable
    assert path.path == "pyproject.toml"
    assert "not valid TOML" in path.reason


# ---------- the report ----------
def judged(tmp_path, root, net=None, **kwargs):
    return run_check(root, registries=registries(tmp_path, net or FakeNet()), installed=lambda name: None, today=TODAY, **kwargs)


def test_the_run_is_not_complete_and_the_command_exits_two(tmp_path):
    report = judged(tmp_path, unreadable_project(tmp_path, "package.json", b"{broken"))
    assert not report.complete
    assert not report.failed, "an unreadable file is not an unsafe finding; it is the check not having happened"
    assert incomplete_text(report) is not None


def test_being_unable_to_read_a_file_outranks_being_unable_to_find_anything_unsafe(tmp_path):
    """The headline, the summary and the text all have to carry it. A clean-looking report is the whole problem."""
    report = judged(tmp_path, unreadable_project(tmp_path, "package.json", b"{broken"))
    text = render_text(report)
    assert "1 file could not be read" in text.splitlines()[0]
    assert "UNREADABLE" in text
    assert "package.json is not valid JSON" in text
    assert render_summary(report) == "stocktake: 1 dependency file could not be read"


def test_the_empty_report_explains_itself_with_the_real_reason(tmp_path):
    """Pointing at the excludes is unhelpful advice when the reason is sitting in the report."""
    report = judged(tmp_path, unreadable_project(tmp_path, "package.json", b"{broken"))
    assert "could not be read, so nothing could be checked" in render_text(report)
    assert "excludes or enabled ecosystems" not in render_text(report)


def test_json_says_it_in_a_field_a_gate_can_read(tmp_path):
    report = judged(tmp_path, unreadable_project(tmp_path, "package.json", b"{broken"))
    data = json.loads(render_json(report))
    assert data["complete"] is False
    assert data["failed"] is False, "a gate that reads `failed` alone cannot tell this from a clean project"
    assert data["unreadable"] == [{"path": "package.json", "reason": data["unreadable"][0]["reason"]}]
    assert "not valid JSON" in data["unreadable"][0]["reason"]


def test_sarif_reports_it_as_an_error_and_the_run_as_unsuccessful(tmp_path):
    report = judged(tmp_path, unreadable_project(tmp_path, "package.json", b"{broken"))
    log = json.loads(render_sarif(report))
    run = log["runs"][0]
    assert run["invocations"][0]["executionSuccessful"] is False
    results = [r for r in run["results"] if r["ruleId"] == "unreadable"]
    assert [r["level"] for r in results] == ["error"]
    assert results[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "package.json"


def test_narrowing_the_report_cannot_hide_it(tmp_path):
    """`--only vulnerable` narrows what was found. It must not narrow away a part of the project that was never looked at."""
    report = judged(tmp_path, unreadable_project(tmp_path, "package.json", b"{broken"))
    assert "UNREADABLE" in render_text(report, "vulnerable")
    log = json.loads(render_sarif(report, "vulnerable"))
    assert any(r["ruleId"] == "unreadable" for r in log["runs"][0]["results"])
    assert json.loads(render_json(report, "vulnerable"))["unreadable"]


# ---------- the exit code and the test item ----------
def test_the_command_exits_two_even_when_it_also_found_something_unsafe(tmp_path):
    """Two says "do not read a verdict into this run", and that has to win: the findings in a partial run are a floor, not an answer."""
    from stocktake.cli import run

    root = tmp_path / "project"
    root.mkdir()
    (root / "Dockerfile").write_text("FROM x\nRUN pip install a==1.0\n", encoding="utf-8")
    (root / "package.json").write_text("{broken", encoding="utf-8")
    net = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")})

    printed: list[str] = []
    code = run(
        ["--root", str(root)],
        registries=registries(tmp_path, net),
        out=printed.append,
        installed=lambda name: None,
        today=TODAY,
    )
    assert code == INCOMPLETE
    assert code != UNSAFE
    assert "VULNERABLE (fix these)" in printed[-1], "the findings are still reported; only the verdict is withheld"


def test_the_pytest_item_fails_rather_than_skipping(tmp_path):
    """A skip would be the softer answer and the wrong one: a suite has no exit code, so a skip makes an unchecked project a green run."""
    from stocktake.pytest_plugin import assert_dependencies_are_safe

    root = unreadable_project(tmp_path, "package.json", b"{broken")
    with pytest.raises(AssertionError, match="could not read 1 dependency file"):
        assert_dependencies_are_safe(root, registries=registries(tmp_path, FakeNet()), installed=lambda name: None, today=TODAY)


def test_both_messages_are_given_and_the_caveat_comes_first():
    """When a run is both partial and unsafe, what the reader needs first is how much of the report to trust."""
    report = Report(findings=(), today=TODAY.isoformat(), unreadable=(Unreadable("package.json", "is not valid JSON"),))
    text = incomplete_text(report)
    assert text is not None
    assert text.splitlines()[0].startswith("StockTake could not read 1 dependency file")
    assert "  package.json is not valid JSON" in text


def test_a_project_can_exclude_a_file_it_knows_is_not_a_manifest(tmp_path):
    """The escape hatch. Fixtures and test data that happen to be named like a manifest are excluded, not accepted: they are not dependencies."""
    root = unreadable_project(tmp_path, "package.json", b"{broken")
    (root / ".stocktake.toml").write_text('exclude = ["package.json"]\n', encoding="utf-8")
    report = judged(tmp_path, root)
    assert report.complete
    assert report.unreadable == ()
