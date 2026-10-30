"""The command: the three exit codes, and the flags that change what is shown rather than what is decided.

A caller should be able to branch on the exit code without parsing anything, so each code gets a test.
"""

import json

from stocktake.cli import INCOMPLETE, OK, UNSAFE, build_parser, run

from helpers import TODAY, FakeNet, advisory_detail, registries


def project(tmp_path, name="project", dockerfile="FROM x\nRUN pip install a==1.0\n"):
    root = tmp_path / name
    root.mkdir()
    (root / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    return root


def check(tmp_path, root, net, argv=(), **kwargs):
    printed: list[str] = []
    code = run(
        [*argv, "--root", str(root)],
        registries=registries(tmp_path, net),
        out=printed.append,
        installed=lambda name: None,
        today=TODAY,
        **kwargs,
    )
    return code, printed[-1] if printed else ""


def test_old_but_safe_exits_zero_and_still_says_what_is_old(tmp_path):
    code, text = check(tmp_path, project(tmp_path), FakeNet(pypi={"a": ("2.0", [])}))
    assert code == OK
    assert "OUTDATED" in text and "a 1.0 -> 2.0 (major)" in text


def test_a_known_vulnerability_exits_one(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")})
    code, text = check(tmp_path, project(tmp_path), net)
    assert code == UNSAFE
    assert "VULNERABLE (fix these)" in text


def test_being_unable_to_reach_the_registries_exits_two_and_says_so_in_json(tmp_path):
    net = FakeNet()
    net.offline = True
    code, text = check(tmp_path, project(tmp_path), net, ["--format", "json"])
    assert code == INCOMPLETE
    assert json.loads(text)["offline"]


def test_a_policy_entry_past_its_date_fails_the_command_and_names_itself(tmp_path):
    root = project(tmp_path)
    (root / ".stocktake.toml").write_text(
        '[[policy.hold_back]]\npackage = "a"\nreason = "needs a rebuild"\nuntil = 2026-01-01\n',
        encoding="utf-8",
    )
    code, text = check(tmp_path, root, FakeNet(pypi={"a": ("2.0", [])}))
    assert code == UNSAFE
    assert "POLICY: hold_back: a was accepted until 2026-01-01" in text
    assert "Dockerfile:2" in text


def test_a_config_file_can_be_pointed_at_from_elsewhere(tmp_path):
    shared = tmp_path / "shared.toml"
    shared.write_text('[[policy.hold_back]]\npackage = "a"\nreason = "shared decision"\nuntil = 2026-12-01\n', encoding="utf-8")
    code, text = check(tmp_path, project(tmp_path), FakeNet(pypi={"a": ("2.0", [])}), ["--config", str(shared)])
    assert code == OK
    assert "held back on purpose: shared decision" in text


def test_a_config_that_cannot_be_read_stops_the_run_rather_than_silently_dropping_the_policy(tmp_path, capsys):
    root = project(tmp_path)
    (root / ".stocktake.toml").write_text("[[policy.hold_back]\n", encoding="utf-8")
    code, _ = check(tmp_path, root, FakeNet(pypi={"a": ("2.0", [])}))
    assert code == INCOMPLETE
    assert "not valid TOML" in capsys.readouterr().err


def test_a_root_that_is_not_a_directory_is_refused(tmp_path, capsys):
    code = run(["--root", str(tmp_path / "nowhere")], registries=registries(tmp_path, FakeNet()), out=lambda text: None, today=TODAY)
    assert code == INCOMPLETE
    assert "is not a directory" in capsys.readouterr().err


def test_the_report_can_be_narrowed_from_the_command_line(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", []), "b": ("2.0", [])}, osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail("bad")})
    root = project(tmp_path, dockerfile="FROM x\nRUN pip install a==1.0 b==1.0\n")
    _code, text = check(tmp_path, root, net, ["--only", "vulnerable"])
    assert "VULNERABLE" in text and "OUTDATED" not in text


def test_every_advisory_can_be_asked_for(tmp_path):
    ids = [f"GHSA-{i:04d}" for i in range(8)]
    net = FakeNet(pypi={"a": ("2.0", [])}, osv={("a", "1.0"): ids}, details={i: advisory_detail("problem", "HIGH") for i in ids})
    root = project(tmp_path)
    _code, brief = check(tmp_path, root, net)
    _code, full = check(tmp_path, root, net, ["--all-advisories"])
    assert brief.count("GHSA-") == 5
    assert full.count("GHSA-") == 8


def test_an_empty_project_reports_nothing_and_exits_zero(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    code, text = check(tmp_path, empty, FakeNet())
    assert code == OK
    assert "Nothing was found to check" in text


def test_the_help_text_explains_the_exit_codes_and_what_leaves_the_machine():
    help_text = build_parser().format_help()
    assert "exit codes:" in help_text
    assert "Only package names and versions leave this machine" in help_text
    for flag in ("--root", "--config", "--format", "--only", "--refresh", "--all-advisories", "--version"):
        assert flag in help_text
