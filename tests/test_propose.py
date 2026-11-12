"""The edit that would fix a finding, worked out and never made.

The tests fall into three groups, and the middle one is the point of the feature: a proposal is only an *edit* when the project keeps that
version by hand. A lock file is generated and a range is resolved against the environment, and printing a hand-edit for either would be
telling somebody to do the wrong thing confidently ([ADR 0014](../docs/adr/0014-propose-prints-an-edit-and-never-makes-one.md)).

The last test is the one that matters most: running this over a project changes nothing in it.
"""

import hashlib
import json

import pytest

from stocktake.check import run_check
from stocktake.cli import run
from stocktake.models import COMMAND, EDIT, MANUAL
from stocktake.propose import proposals, target_version
from stocktake.report import render_propose, shown_statuses

from helpers import TODAY, FakeNet, advisory_detail, registries


def project(tmp_path, files):
    root = tmp_path / "project"
    root.mkdir()
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def judged(tmp_path, root, net, **kwargs):
    return run_check(root, registries=registries(tmp_path, net), installed=lambda name: None, today=TODAY, **kwargs)


def vulnerable(name="pillow", version="9.0.0", latest="12.0.0", fixed=("10.0.0",)):
    return FakeNet(
        pypi={name: (latest, [])},
        osv={(name, version): ["GHSA-1"]},
        details={"GHSA-1": advisory_detail("bad", "HIGH", fixed=list(fixed), package=name)},
    )


def made(tmp_path, root, net, only="all", **kwargs):
    return proposals(judged(tmp_path, root, net, **kwargs), root, shown_statuses(only))


# ---------- an edit, where the project keeps the version by hand ----------
def test_a_pinned_requirement_gets_the_line_as_it_stands_and_as_it_would_be(tmp_path):
    root = project(tmp_path, {"requirements.txt": "flask==1.0\npillow==9.0.0\n"})
    (proposal,) = made(tmp_path, root, vulnerable())
    assert proposal.kind == EDIT
    assert (proposal.path, proposal.line) == ("requirements.txt", 2)
    assert proposal.before == "pillow==9.0.0"
    assert proposal.after == "pillow==10.0.0", "the version that clears the advisory, not the newest"


def test_a_dockerfile_pin_is_edited_in_place_on_its_run_line(tmp_path):
    root = project(tmp_path, {"Dockerfile": "FROM scratch\nRUN pip install pillow==9.0.0 six==1.0\n"})
    (proposal,) = made(tmp_path, root, vulnerable())
    assert proposal.before == "RUN pip install pillow==9.0.0 six==1.0"
    assert proposal.after == "RUN pip install pillow==10.0.0 six==1.0"


def test_a_workflow_pin_keeps_its_at_sign_and_its_v(tmp_path):
    root = project(tmp_path, {".github/workflows/ci.yml": "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v2\n"})
    net = FakeNet(github={"actions/checkout": "v7.0.1"})
    (proposal,) = made(tmp_path, root, net)
    assert proposal.after.strip() == "- uses: actions/checkout@v7", "a moving tag, cut back to the precision written"


def test_a_pre_commit_rev_is_edited(tmp_path):
    config = "repos:\n  - repo: https://github.com/astral-sh/ruff-pre-commit\n    rev: v0.6.9\n    hooks:\n      - id: ruff\n"
    root = project(tmp_path, {".pre-commit-config.yaml": config})
    net = FakeNet(github={"astral-sh/ruff-pre-commit": "v0.17.4"})
    (proposal,) = made(tmp_path, root, net)
    assert proposal.before.strip() == "rev: v0.6.9"
    assert proposal.after.strip() == "rev: v0.17.4"


def test_a_base_image_keeps_its_variant(tmp_path):
    """`python:3.12-slim` must not be proposed as `python:3.15.2`, which is a different image."""
    root = project(tmp_path, {"Dockerfile": "FROM python:3.12-slim\n"})
    net = FakeNet(docker={"library/python": ["3.12", "3.12-slim", "3.15", "3.15-slim", "3.15.2-slim"]})
    (proposal,) = made(tmp_path, root, net)
    assert proposal.before == "FROM python:3.12-slim"
    assert proposal.after == "FROM python:3.15-slim"


def test_a_moving_tag_is_cut_back_to_the_precision_the_project_wrote(tmp_path):
    """Somebody tracking `3.12` is choosing to follow that line; `3.15` is the tag they want, not `3.15.2` (ADR 0008)."""
    root = project(tmp_path, {"Dockerfile": "FROM python:3.12\n"})
    net = FakeNet(docker={"library/python": ["3.12", "3.15", "3.15.2"]})
    (proposal,) = made(tmp_path, root, net)
    assert proposal.target == "3.15"


# ---------- a command, where an edit would be wrong ----------
def test_a_lock_file_is_a_command_and_says_why(tmp_path):
    """Hand-editing a lock produces one that disagrees with itself."""
    lock = json.dumps({"name": "x", "lockfileVersion": 3, "packages": {"node_modules/lodash": {"version": "4.17.15"}}})
    root = project(tmp_path, {"package-lock.json": lock})
    net = FakeNet(
        npm={"lodash": "4.18.0"},
        osv={("lodash", "4.17.15"): ["GHSA-1"]},
        details={"GHSA-1": advisory_detail("bad", "HIGH", fixed=["4.17.21"], package="lodash")},
    )
    (proposal,) = made(tmp_path, root, net)
    assert proposal.kind == COMMAND
    assert proposal.command == "npm install lodash@4.17.21"
    assert "generated" in proposal.note
    assert not proposal.before and not proposal.after, "no edit is offered for a file nobody should hand-edit"


@pytest.mark.parametrize(
    ("lock", "command"),
    [
        ("uv.lock", "uv lock --upgrade-package pillow"),
        ("poetry.lock", "poetry update pillow"),
        ("pdm.lock", "pdm update pillow"),
    ],
)
def test_each_python_lock_gets_its_own_tool(tmp_path, lock, command):
    text = '[[package]]\nname = "pillow"\nversion = "9.0.0"\n'
    root = project(tmp_path, {lock: text})
    (proposal,) = made(tmp_path, root, vulnerable())
    assert proposal.kind == COMMAND
    assert proposal.command == command


def test_a_range_resolved_from_the_environment_is_a_command_not_a_file_edit(tmp_path):
    """`pyproject.toml` saying `pillow>=8` is not wrong when the installed pillow is old. The file needs no edit; the environment does."""
    root = project(tmp_path, {"pyproject.toml": '[project]\nname = "x"\ndependencies = ["pillow>=8"]\n'})
    report = run_check(
        root,
        registries=registries(tmp_path, vulnerable()),
        installed=lambda name: "9.0.0" if name == "pillow" else None,
        today=TODAY,
    )
    (proposal,) = proposals(report, root)
    assert proposal.kind == COMMAND
    assert proposal.command == 'pip install --upgrade "pillow==10.0.0"'
    assert "declares a range" in proposal.note


# ---------- when there is nothing to propose ----------
def test_a_vulnerability_with_no_published_fix_says_so_rather_than_inventing_one(tmp_path):
    root = project(tmp_path, {"requirements.txt": "pillow==9.0.0\n"})
    net = FakeNet(
        pypi={"pillow": ("9.0.0", [])},
        osv={("pillow", "9.0.0"): ["GHSA-1"]},
        details={"GHSA-1": advisory_detail("bad", "HIGH")},
    )
    (proposal,) = made(tmp_path, root, net)
    assert proposal.kind == MANUAL
    assert proposal.target == ""
    assert "no fixed version" in proposal.note


def test_nothing_is_proposed_for_what_needs_no_action(tmp_path):
    """Current, held, accepted and unknown are all decided or unknowable; none of them is an upgrade somebody has to make."""
    root = project(tmp_path, {"requirements.txt": "flask==3.0.0\n"})
    assert made(tmp_path, root, FakeNet(pypi={"flask": ("3.0.0", [])})) == []


def test_an_unknown_dependency_gets_no_proposal(tmp_path):
    root = project(tmp_path, {"requirements.txt": "nosuchpackage==1.0\n"})
    assert made(tmp_path, root, FakeNet()) == []


def test_narrowing_applies_here_too(tmp_path):
    root = project(tmp_path, {"requirements.txt": "pillow==9.0.0\nsix==1.0\n"})
    net = vulnerable()
    net.pypi["six"] = ("2.0", [])
    assert len(made(tmp_path, root, net, only="all")) == 2
    assert [p.finding.dep.name for p in made(tmp_path, root, net, only="vulnerable")] == ["pillow"]


def test_the_worst_comes_first(tmp_path):
    root = project(tmp_path, {"requirements.txt": "six==1.0\npillow==9.0.0\n"})
    net = vulnerable()
    net.pypi["six"] = ("2.0", [])
    assert [p.finding.status for p in made(tmp_path, root, net)] == ["vulnerable", "outdated"]


# ---------- the safety properties ----------
def test_no_edit_is_offered_when_the_version_is_not_exactly_once_on_the_line(tmp_path):
    """An edit that is nearly right is worse than a sentence saying what to do."""
    root = project(tmp_path, {"Dockerfile": "FROM scratch\nRUN pip install pillow==9.0.0 other==9.0.0\n"})
    net = vulnerable()
    net.pypi["other"] = ("9.0.0", [])
    (proposal,) = [p for p in made(tmp_path, root, net) if p.finding.dep.name == "pillow"]
    assert proposal.kind == EDIT, "the name makes this one unambiguous"
    assert proposal.after == "RUN pip install pillow==10.0.0 other==9.0.0", "only the one package moved"


def test_running_propose_over_a_project_changes_nothing_in_it(tmp_path):
    """The rule this whole feature lives under: it prints the edit and never makes it."""
    files = {
        "requirements.txt": "pillow==9.0.0\n",
        "Dockerfile": "FROM python:3.12-slim\nRUN pip install pillow==9.0.0\n",
        ".pre-commit-config.yaml": "repos:\n  - repo: https://github.com/a/b\n    rev: v1.0.0\n    hooks:\n      - id: x\n",
    }
    root = project(tmp_path, files)
    net = vulnerable()
    net.github["a/b"] = "v2.0.0"

    def fingerprint():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}

    before = fingerprint()
    rendered = render_propose(made(tmp_path, root, net))
    assert fingerprint() == before, "propose opened these files and must not have written to any of them"
    assert "pillow==10.0.0" in rendered, "and it did actually produce the edit it was asked for"


def test_the_rendered_output_is_plain_ascii(tmp_path):
    """It lands in the same terminals the report does, and an em-dash came out as `?` there once already."""
    root = project(tmp_path, {"requirements.txt": "pillow==9.0.0\n", "Dockerfile": "FROM python:3.12-slim\n"})
    net = vulnerable()
    net.docker = {"library/python": ["3.12", "3.15"]}
    rendered = render_propose(made(tmp_path, root, net))
    assert rendered.isascii(), sorted({c for c in rendered if not c.isascii()})


def test_the_header_says_it_never_applies_them(tmp_path):
    root = project(tmp_path, {"requirements.txt": "pillow==9.0.0\n"})
    assert "never applies them" in render_propose(made(tmp_path, root, vulnerable()))


def test_nothing_to_propose_says_so_rather_than_printing_an_empty_heading():
    assert "Nothing to propose" in render_propose([])


def test_the_target_for_a_withdrawn_release_is_the_newest(tmp_path):
    root = project(tmp_path, {"requirements.txt": "pillow==9.0.0\n"})
    (proposal,) = made(tmp_path, root, FakeNet(pypi={"pillow": ("12.0.0", ["9.0.0"])}))
    assert proposal.target == "12.0.0"
    assert "withdrawn" in proposal.reason


def test_target_version_is_none_for_a_finding_with_no_action():
    from stocktake.models import Dep, Finding

    assert target_version(Finding(Dep("PyPI", "a", "1.0", "x"), "current", "ok", "1.0")) is None


# ---------- through the command ----------
def test_the_command_renders_it_and_still_exits_on_the_findings(tmp_path):
    root = project(tmp_path, {"requirements.txt": "pillow==9.0.0\n"})
    printed: list[str] = []
    code = run(
        ["--root", str(root), "--format", "propose"],
        registries=registries(tmp_path, vulnerable()),
        out=printed.append,
        installed=lambda name: None,
        today=TODAY,
    )
    assert code == 1, "the exit code is about what was found, not about how it was printed"
    assert "+ pillow==10.0.0" in printed[-1]
