"""Reading GitHub Actions pins out of a workflow.

Four kinds of ref, and the difference between them matters more here than anywhere else in the tool: a full version tag is a pin, a
major-only tag is a range that GitHub advances, a commit SHA is the strictest pin of all and unreadable without help, and a branch name is
not a version at all. Calling any of them by the wrong name produces a report people stop reading.
"""

import re

from stocktake.readers.base import Context
from stocktake.readers.workflows import COMMIT_NOTE, MOVING_NOTE, is_workflow, read_workflow_actions, workflow_uses

WORKFLOW = """name: CI

on: [push]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7.1.0
      - uses: actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830  # v4.2.0
      - uses: some/action@08c6903cd8c0fde910a37f88322edcfb5dd907a8
      - uses: risky/action@main
      - uses: ./.github/actions/local-thing
      - uses: docker://alpine:3.20
      - name: Not a uses line
        run: echo "uses: not/this@v1"
      - uses: 'quoted/action@v2'
      - uses: owner/repo/.github/workflows/reusable.yml@v3
"""


def read(tmp_path, text=WORKFLOW, name="ci.yml"):
    path = tmp_path / ".github" / "workflows" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return list(read_workflow_actions(path, text, Context(root=tmp_path, installed=lambda n: None)))


# ---------- which files ----------
def test_workflows_and_action_definitions_are_read(tmp_path):
    assert is_workflow(tmp_path / ".github" / "workflows" / "ci.yml")
    assert is_workflow(tmp_path / ".github" / "workflows" / "release.yaml")
    assert is_workflow(tmp_path / ".github" / "actions" / "thing" / "action.yml")
    assert is_workflow(tmp_path / "action.yaml")


def test_other_yaml_is_left_alone(tmp_path):
    # Reading every .yml in a repository would mean guessing, and guessing wrong noisily.
    assert not is_workflow(tmp_path / "docker-compose.yml")
    assert not is_workflow(tmp_path / ".github" / "dependabot.yml")
    assert not is_workflow(tmp_path / ".pre-commit-config.yaml")
    assert not is_workflow(tmp_path / ".github" / "workflows" / "notes.md")


# ---------- which refs ----------
def test_every_action_is_found_with_the_line_it_is_on(tmp_path):
    deps = read(tmp_path)
    assert [(d.name, d.version, d.spec, d.source.split(":")[1]) for d in deps] == [
        ("actions/checkout", "7", "@v7", "9"),
        ("actions/setup-python", "7.1.0", "@v7.1.0", "10"),
        ("actions/cache", "4.2.0", "@0057852bfaa89a56745cba8c7296529d2fc39830", "11"),
        ("some/action", None, "@08c6903cd8c0fde910a37f88322edcfb5dd907a8", "12"),
        ("risky/action", None, "@main", "13"),
        ("quoted/action", "2", "@v2", "18"),
        ("owner/repo", "3", "@v3", "19"),
    ]
    assert all(d.ecosystem == "GitHub" and d.role == "ci" for d in deps)


def test_a_major_only_tag_is_marked_as_one_that_moves(tmp_path):
    deps = {d.name: d for d in read(tmp_path)}
    assert deps["actions/checkout"].moving is True, "GitHub advances @v7 as it releases, so a new v7 patch is not an update to make"
    assert deps["actions/setup-python"].moving is False, "nobody moves a full version tag"


def test_a_commit_pin_takes_its_version_from_the_conventional_comment(tmp_path):
    cache = next(d for d in read(tmp_path) if d.name == "actions/cache")
    assert (cache.version, cache.moving, cache.note) == ("4.2.0", False, "")


def test_a_commit_pin_with_no_comment_says_why_it_cannot_be_compared(tmp_path):
    action = next(d for d in read(tmp_path) if d.name == "some/action")
    assert action.version is None
    assert action.note == COMMIT_NOTE
    assert "name the version in a comment" in action.note, "the note has to say what would fix it"


def test_a_branch_ref_says_that_it_moves_which_is_a_different_problem(tmp_path):
    action = next(d for d in read(tmp_path) if d.name == "risky/action")
    assert (action.version, action.note) == (None, MOVING_NOTE)
    assert action.note != COMMIT_NOTE, "pinned too loosely and pinned unreadably are not the same finding"


def test_the_repositorys_own_actions_and_containers_are_not_registry_dependencies(tmp_path):
    names = {d.name for d in read(tmp_path)}
    assert not any(name.startswith(".") for name in names)
    assert "alpine" not in names and "docker" not in names


def test_a_uses_string_inside_a_run_block_is_not_a_dependency(tmp_path):
    assert "not/this" not in {d.name for d in read(tmp_path)}


def test_a_reusable_workflow_is_a_dependency_on_its_repository(tmp_path):
    # `owner/repo/.github/workflows/reusable.yml@v3` is a dependency on owner/repo, not on a package called ".github".
    assert next(d for d in read(tmp_path) if d.name == "owner/repo").version == "3"


def test_a_uses_line_with_no_ref_is_skipped_rather_than_guessed_at(tmp_path):
    assert read(tmp_path, "jobs:\n  a:\n    steps:\n      - uses: actions/checkout\n") == []


def test_an_empty_workflow_yields_nothing(tmp_path):
    assert read(tmp_path, "") == []
    assert read(tmp_path, "name: CI\non: [push]\n") == []


def test_the_ref_is_kept_as_written_so_the_report_can_show_it(tmp_path):
    assert {d.spec for d in read(tmp_path)} >= {"@v7", "@main", "@0057852bfaa89a56745cba8c7296529d2fc39830"}


# ---------- the guard ----------
def test_no_action_in_the_workflow_escapes_the_reader(tmp_path):
    """Counts `uses:` references with a plain regex, independently of the reader, excluding the local and container ones."""
    expected = set()
    for line in WORKFLOW.splitlines():
        match = re.match(r"\s*-\s+uses:\s*['\"]?([^'\"\s#]+)", line)
        if not match:
            continue
        value = match.group(1)
        if value.startswith(("./", "docker://")) or "@" not in value:
            continue
        expected.add("/".join(value.split("@")[0].split("/")[:2]))
    found = {d.name for d in read(tmp_path)}
    assert expected == found, f"the reader and an independent count disagree about {expected ^ found}"


def test_every_action_found_is_reported_exactly_once(tmp_path):
    uses = workflow_uses(WORKFLOW)
    assert len(uses) == len(read(tmp_path))
    assert len({(u.repo, u.line) for u in uses}) == len(uses)
