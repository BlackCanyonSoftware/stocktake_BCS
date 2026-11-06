"""The YAML subset, and the refusals that make a subset safe.

Half the tests here are about what it will **not** read. That is the design: the objection to reading YAML without a library was that a
half-parser silently mis-reads things, and the answer is not to be a whole parser but to stop at the edge and say so, which only became a
safe thing to do when [ADR 0009](../docs/adr/0009-an-unread-file-makes-the-run-incomplete.md) gave "I could not read this" an exit code
([ADR 0013](../docs/adr/0013-a-strict-yaml-subset-rather-than-a-dependency.md)).
"""

import pytest

from stocktake.readers.base import UnreadableManifest
from stocktake.readers.yamlish import parse

PRECOMMIT = """# Install once:  pre-commit install
default_language_version:
  python: python3.11

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
        exclude: ^(src/brand/|tests/golden/)
      - id: mixed-line-ending
        args: [--fix=lf]
  - repo: local
    hooks:
      - id: no-raw-inbox
        name: data/inbox/ must not be committed
        entry: >-
          bash -c 'if git diff --cached | grep -q "^data/"; then
          echo "nope"; exit 1; fi'
        language: system
"""


# ---------- what it reads ----------
def test_it_reads_the_shape_a_pre_commit_config_actually_has():
    data = parse(PRECOMMIT)
    assert data["default_language_version"] == {"python": "python3.11"}
    assert [r["repo"] for r in data["repos"]] == ["https://github.com/pre-commit/pre-commit-hooks", "local"]
    assert data["repos"][0]["rev"] == "v5.0.0"


def test_a_sequence_of_mappings_keeps_every_key_of_each():
    hooks = parse(PRECOMMIT)["repos"][0]["hooks"]
    assert [h["id"] for h in hooks] == ["trailing-whitespace", "mixed-line-ending"]
    assert hooks[0]["exclude"] == "^(src/brand/|tests/golden/)"


def test_a_value_holding_a_pipe_is_not_mistaken_for_a_block_scalar():
    """`|` opens a block scalar only as the whole value. A regex full of alternations is a plain scalar that happens to contain one."""
    assert parse("exclude: ^(a|b|c)$\n") == {"exclude": "^(a|b|c)$"}


def test_a_folded_block_scalar_is_consumed_rather_than_read_as_structure():
    """A real config has one holding a shell command. A reader that did not know where it ended would read its continuation as keys."""
    entry = parse(PRECOMMIT)["repos"][1]["hooks"][0]
    assert "bash -c" in entry["entry"]
    assert entry["language"] == "system", "the key after the block scalar is still found"


def test_a_comment_after_a_value_is_not_part_of_it():
    assert parse("rev: v5.0.0   # must match pyproject\n") == {"rev": "v5.0.0"}


def test_a_hash_inside_a_value_or_a_quote_is_not_a_comment():
    """YAML's own rule: a `#` starts a comment only after whitespace."""
    assert parse("exclude: ^a#b$\n") == {"exclude": "^a#b$"}
    assert parse('name: "a # b"\n') == {"name": "a # b"}


def test_a_url_value_is_not_split_on_its_colon():
    assert parse("repo: https://github.com/owner/name\n") == {"repo": "https://github.com/owner/name"}


def test_quotes_are_removed_from_a_simply_quoted_scalar():
    assert parse("lockfileVersion: '9.0'\n") == {"lockfileVersion": "9.0"}


def test_a_flow_collection_is_kept_as_text_because_nothing_reads_inside_it():
    """Structure is parsed; leaves are text. Not parsing what nothing reads is most of why this is small enough to trust."""
    assert parse("args: [--fix=lf]\n") == {"args": "[--fix=lf]"}


def test_a_key_with_nothing_under_it_is_empty_rather_than_a_guess():
    assert parse("repos:\n") == {"repos": ""}


def test_an_empty_document_is_an_empty_mapping():
    assert parse("") == {}
    assert parse("# only a comment\n") == {}


def test_a_nested_sequence_under_a_dash_is_read():
    data = parse("- a: 1\n  b:\n    - x\n    - y\n")
    assert data == [{"a": "1", "b": ["x", "y"]}]


# ---------- what it refuses ----------
@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("base: &anchor\n  a: 1\n", "anchor"),
        ("copy: *anchor\n", "alias"),
        ("when: !!timestamp 2026-01-01\n", "tag"),
        ("merged:\n  <<: *base\n  a: 1\n", "merge key"),
        ("a: 1\n---\nb: 2\n", "more than one YAML document"),
        ("a:\n\tb: 1\n", "tab"),
    ],
)
def test_a_construct_it_does_not_implement_is_refused_loudly(text, why):
    """Refused, never guessed at. A quiet mis-read is the failure this whole approach is accountable for avoiding."""
    with pytest.raises(UnreadableManifest, match=why):
        parse(text)


def test_the_refusal_names_the_file_and_the_line():
    with pytest.raises(UnreadableManifest) as caught:
        parse("ok: 1\nbad: &anchor\n  x: 1\n", ".pre-commit-config.yaml")
    message = str(caught.value)
    assert ".pre-commit-config.yaml" in message
    assert "line 2" in message


def test_a_document_it_cannot_finish_is_refused_rather_than_half_returned():
    """A partial parse is the silent half-read this must never do: whatever was found is thrown away with the reason."""
    with pytest.raises(UnreadableManifest, match="could not be read past"):
        parse("a: 1\n  oops: 2\n   worse: 3\n")
