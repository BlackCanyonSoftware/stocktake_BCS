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


UNSET = object()


def check(tmp_path, root, net, argv=(), installed=UNSET, **kwargs):
    """Run the command. By default nothing is installed anywhere; pass `installed=None` to exercise the environment resolution itself."""
    printed: list[str] = []
    code = run(
        [*argv, "--root", str(root)],
        registries=registries(tmp_path, net),
        out=printed.append,
        installed=(lambda name: None) if installed is UNSET else installed,
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


def test_a_project_that_disables_an_ecosystem_makes_no_request_for_it(tmp_path):
    """The whole point of per-project ecosystems: a project that only wants its Python pins checked never asks about anything else."""
    root = project(
        tmp_path, dockerfile='FROM x\nRUN pip install a==1.0\nRUN curl -LO "https://github.com/o/r/releases/download/v1.2.3/r.tar.gz"\n'
    )
    net = FakeNet(pypi={"a": ("1.0", [])}, github={"o/r": "v2.0.0"})

    code, text = check(tmp_path, root, net)
    assert code == OK
    assert net.asked_about("api.github.com"), "with everything enabled, the release binary is checked"
    assert "o/r" in text

    (root / ".stocktake.toml").write_text('ecosystems = ["python"]\n', encoding="utf-8")
    quiet = FakeNet(pypi={"a": ("1.0", [])}, github={"o/r": "v2.0.0"})
    code, text = check(tmp_path, root, quiet)
    assert code == OK
    assert not quiet.asked_about("api.github.com"), "with binaries disabled, GitHub is never asked"
    assert "o/r" not in text


def test_a_project_can_accept_a_manifest_it_knows_is_unreadable(tmp_path):
    root = project(tmp_path)
    (root / "go.mod").write_text("module x\n", encoding="utf-8")

    _code, text = check(tmp_path, root, FakeNet(pypi={"a": ("1.0", [])}))
    assert "UNREAD" in text and "go.mod" in text

    (root / ".stocktake.toml").write_text('accept_unread = ["go.mod"]\n', encoding="utf-8")
    _code, quiet_text = check(tmp_path, root, FakeNet(pypi={"a": ("1.0", [])}), ["--format", "json"])
    assert json.loads(quiet_text)["unread_manifests"] == []
    assert json.loads(quiet_text)["accepted_unread"] == ["go.mod"], "accepted, but never invisible"


# ---------- which environment the ranges are resolved against ----------
def declaring_project(tmp_path, name="declaring"):
    root = tmp_path / name
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "x"\ndependencies = ["flask>=2"]\n', encoding="utf-8")
    return root


def venv_at(base, *packages):
    site = base / "Lib" / "site-packages"
    site.mkdir(parents=True)
    for package in packages:
        (site / f"{package}.dist-info").mkdir()
    return base


def test_a_project_whose_environment_cannot_be_found_is_told_so_rather_than_given_a_wrong_version(tmp_path):
    code, text = check(tmp_path, declaring_project(tmp_path), FakeNet(), installed=None)
    assert code == OK
    assert "NOTE: No Python environment was found" in text
    assert "--environment PATH" in text, "the note has to say what to do about it"


def test_the_projects_own_venv_is_used_without_being_asked(tmp_path):
    root = declaring_project(tmp_path)
    venv_at(root / ".venv", "flask-3.0.0")
    code, text = check(tmp_path, root, FakeNet(pypi={"flask": ("3.0.0", [])}), installed=None)
    assert code == OK
    assert "NOTE:" not in text
    assert "CURRENT: 1 up to date" in text


def test_an_environment_can_be_named_on_the_command_line(tmp_path):
    root = declaring_project(tmp_path)
    elsewhere = venv_at(tmp_path / "elsewhere", "flask-2.0.0")
    net = FakeNet(pypi={"flask": ("3.0.0", [])})
    code, text = check(tmp_path, root, net, ["--environment", str(elsewhere)], installed=None)
    assert code == OK
    assert "flask 2.0.0 -> 3.0.0 (major)" in text


def test_an_environment_can_be_named_in_the_config_relative_to_the_project(tmp_path):
    root = declaring_project(tmp_path)
    venv_at(root / "tools" / "env", "flask-2.0.0")
    (root / ".stocktake.toml").write_text('environment = "tools/env"\n', encoding="utf-8")
    code, text = check(tmp_path, root, FakeNet(pypi={"flask": ("3.0.0", [])}), installed=None)
    assert code == OK
    assert "flask 2.0.0 -> 3.0.0 (major)" in text


def test_being_pointed_at_something_that_is_not_an_environment_stops_the_run(tmp_path, capsys):
    root = declaring_project(tmp_path)
    (tmp_path / "notanenv").mkdir()
    code, _ = check(tmp_path, root, FakeNet(), ["--environment", str(tmp_path / "notanenv")], installed=None)
    assert code == INCOMPLETE
    assert "no Python environment found at" in capsys.readouterr().err


def test_the_note_is_left_out_when_no_declared_range_went_unresolved(tmp_path):
    # A Dockerfile's unpinned install is about what the image will build, not about which environment we looked in.
    root = project(tmp_path, dockerfile="FROM x\nRUN pip install a\n")
    _code, text = check(tmp_path, root, FakeNet(), installed=None)
    assert "NOTE:" not in text
    assert "UNPINNED" in text


def test_the_help_text_explains_the_exit_codes_and_what_leaves_the_machine():
    help_text = build_parser().format_help()
    assert "exit codes:" in help_text
    assert "Only package names and versions leave this machine" in help_text
    for flag in ("--root", "--config", "--format", "--only", "--refresh", "--all-advisories", "--version"):
        assert flag in help_text
