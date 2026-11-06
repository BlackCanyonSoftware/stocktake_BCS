"""Reading `.pre-commit-config.yaml`: the hook versions a repository gates its own commits with.

The last test is the guard: it counts the `repo`/`rev` pairs with a plain regular expression, independently of the reader and of the YAML
subset underneath it, and fails if the two disagree.
"""

import re

import pytest

from stocktake.readers.base import Context, UnreadableManifest
from stocktake.readers.precommit import is_precommit, read_precommit_hooks, repository_of

CONFIG = """# Install once:  pre-commit install
default_language_version:
  python: python3.11

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: mixed-line-ending
        args: [--fix=lf]

  - repo: https://github.com/astral-sh/ruff-pre-commit
    # Must equal the ruff pin in pyproject.toml.
    rev: v0.14.1
    hooks:
      - id: ruff

  - repo: https://github.com/psf/black
    rev: 24.8.0
    hooks:
      - id: black

  - repo: https://github.com/some/pinned
    rev: 9f1c2d3e4b5a69788899aabbccddeeff00112233  # v2.1.0
    hooks:
      - id: thing

  - repo: https://github.com/tracks/major
    rev: v3
    hooks:
      - id: tracker

  - repo: https://gitlab.com/elsewhere/hooks
    rev: v1.0.0
    hooks:
      - id: nothing-we-can-ask-about

  - repo: local
    hooks:
      - id: house-rule
        name: a rule defined right here
        language: fail
        entry: not allowed
"""


def read(tmp_path, text=CONFIG):
    path = tmp_path / ".pre-commit-config.yaml"
    path.write_text(text, encoding="utf-8")
    return list(read_precommit_hooks(path, text, Context(root=tmp_path, installed=lambda name: None)))


def test_it_finds_every_hook_repository_that_names_a_version(tmp_path):
    found = {d.name: d for d in read(tmp_path)}
    assert found["pre-commit/pre-commit-hooks"].version == "5.0.0"
    assert found["astral-sh/ruff-pre-commit"].version == "0.14.1"
    assert found["psf/black"].version == "24.8.0", "a rev with no leading v is still a version"


def test_local_hooks_are_not_a_dependency(tmp_path):
    """`local` and `meta` are pre-commit's own words for "defined right here". There is nobody to ask about them."""
    assert "local" not in {d.name for d in read(tmp_path)}


def test_a_hook_hosted_somewhere_with_no_client_is_left_alone(tmp_path):
    """Reported as nothing rather than as an `unknown` nobody can act on; it appears the day there is something to ask."""
    assert not any("gitlab" in d.name or "elsewhere" in d.name for d in read(tmp_path))


def test_a_commit_pinned_rev_takes_its_version_from_the_comment_beside_it(tmp_path):
    """The same convention the workflows reader reads, because it is the same rule and it is imported rather than rewritten."""
    found = {d.name: d for d in read(tmp_path)}
    assert found["some/pinned"].version == "2.1.0"


def test_a_major_only_rev_is_a_moving_tag(tmp_path):
    """`v3` is advanced by its publisher, so only a change at the precision written counts (ADR 0008)."""
    found = {d.name: d for d in read(tmp_path)}
    assert found["tracks/major"].moving is True
    assert found["astral-sh/ruff-pre-commit"].moving is False, "a full version tag is one nobody moves"


def test_every_finding_points_at_the_rev_line_which_is_the_one_to_edit(tmp_path):
    found = {d.name: d for d in read(tmp_path)}
    assert found["pre-commit/pre-commit-hooks"].source == ".pre-commit-config.yaml:7"
    assert found["astral-sh/ruff-pre-commit"].source == ".pre-commit-config.yaml:15", "past the comment between repo and rev"


def test_the_findings_are_github_refs_used_by_ci(tmp_path):
    for dep in read(tmp_path):
        assert dep.ecosystem == "GitHub"
        assert dep.role == "ci"


def test_a_config_this_cannot_fully_read_is_refused_rather_than_half_read(tmp_path):
    """The whole bargain of reading YAML without a library: stop at the edge, loudly, and let ADR 0009 make it an incomplete run."""
    with pytest.raises(UnreadableManifest, match="anchor"):
        read(tmp_path, "repos: &base\n  - repo: https://github.com/a/b\n    rev: v1.0.0\n")


def test_a_config_with_no_repos_at_all_is_fine(tmp_path):
    assert read(tmp_path, "default_language_version:\n  python: python3.11\n") == []


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/owner/name", "owner/name"),
        ("https://github.com/owner/name.git", "owner/name"),
        ("https://github.com/owner/name/", "owner/name"),
        ("local", None),
        ("meta", None),
        ("https://gitlab.com/owner/name", None),
        ("https://github.com/owner", None),
    ],
)
def test_which_repository_a_hook_url_names(url, expected):
    assert repository_of(url) == expected


def test_both_spellings_of_the_filename_are_recognised(tmp_path):
    assert is_precommit(tmp_path / ".pre-commit-config.yaml")
    assert is_precommit(tmp_path / ".pre-commit-config.yml")
    assert not is_precommit(tmp_path / "pre-commit-config.yaml")


# ---------- the guard ----------
def test_no_pinned_hook_repository_escapes_the_reader(tmp_path):
    """Counts `repo`/`rev` pairs with an independent regular expression, and insists the reader agrees.

    Deliberately not routed through the YAML subset: the point of a guard is that it would still fail if that subset were wrong.
    """
    expected = set()
    pending = None
    for line in CONFIG.splitlines():
        repo = re.match(r"^\s*-?\s*repo:\s*(\S+)", line)
        if repo:
            pending = repo.group(1)
            continue
        rev = re.match(r"^\s*rev:\s*(\S+)", line)
        if rev and pending and pending.startswith("https://github.com/"):
            expected.add("/".join(pending[len("https://github.com/") :].removesuffix(".git").strip("/").split("/")[:2]))
            pending = None

    found = {d.name for d in read(tmp_path)}
    assert expected == found, f"the reader and an independent count disagree about: {expected ^ found}"
