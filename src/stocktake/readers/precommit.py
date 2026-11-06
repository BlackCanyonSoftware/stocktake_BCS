"""`.pre-commit-config.yaml`: the hook versions a repository gates its own commits with.

A pre-commit `rev` is a GitHub ref and nothing more exotic, so the rules for reading one already exist in `workflows.py` and are imported
rather than written a second time: a full version tag is a pin, `v1` and `v1.2` are tags their publisher advances
([ADR 0008](adr/0008-a-tag-its-publisher-moves-is-a-range.md)), and a commit SHA has no version unless a comment beside it names one.

`repo: local` and `repo: meta` are pre-commit's own words for "the hooks are defined here", so there is nothing to ask anybody about.

The file is YAML, which StockTake reads through its own strict subset rather than a dependency
([ADR 0013](adr/0013-a-strict-yaml-subset-rather-than-a-dependency.md)). A construct that subset does not implement makes the file
unreadable and the run incomplete, which is the point: a config this could only half-read is one it must not quietly half-check.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from stocktake.models import Dep
from stocktake.readers.base import Context, reader
from stocktake.readers.workflows import github_ref
from stocktake.readers.yamlish import parse

FILE_NAMES = frozenset({".pre-commit-config.yaml", ".pre-commit-config.yml"})

# pre-commit's own reserved values for "these hooks live in this repository", neither of which names anything a registry knows.
NOT_A_REPOSITORY = frozenset({"local", "meta"})

GITHUB = "https://github.com/"


def is_precommit(path: Path) -> bool:
    return path.name in FILE_NAMES


def repository_of(url: str) -> str | None:
    """`owner/repo` for a GitHub URL, or None for anywhere else.

    Only GitHub is resolved because only GitHub has a client here. A hook hosted on GitLab is left alone rather than reported as an
    `unknown` nobody can act on; it will show up the day there is something to ask.
    """
    if url.lower() in NOT_A_REPOSITORY or not url.lower().startswith(GITHUB):
        return None
    segments = url[len(GITHUB) :].removesuffix(".git").strip("/").split("/")
    return "/".join(segments[:2]) if len(segments) >= 2 else None


def locate_rev(text: str, url: str) -> tuple[int, str]:
    """The line this repository's `rev:` is written on, and whatever comment trails it.

    Two things the parser cannot give. It returns plain data with no positions, and threading one through every value to label a single key
    would be most of the cost of a real YAML library; and it strips comments, where a commit-pinned `rev` keeps its `# v2.1.0`. So the
    positions come from a second, independent pass over the raw lines.

    The `rev:` line rather than the `repo:` line, because that is the line somebody edits. Two entries for one repository would both be
    pointed at the first, which is the known limit of doing it this way.
    """
    current = ""
    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip().lstrip("-").strip()
        if stripped.startswith("repo:"):
            current = stripped[len("repo:") :].strip().strip("'\"")
        elif stripped.startswith("rev:") and current == url:
            _, _, comment = stripped.partition("#")
            return number, comment
    return 0, ""


def hook_repositories(data: Any) -> list[tuple[str, str]]:
    """Every `(repo, rev)` the config declares, as written. Entries with no `rev` are left out: there is no version in them."""
    repos = data.get("repos") if isinstance(data, dict) else None
    if not isinstance(repos, list):
        return []
    found = []
    for entry in repos:
        if not isinstance(entry, dict):
            continue
        url, rev = entry.get("repo"), entry.get("rev")
        if isinstance(url, str) and isinstance(rev, str) and url and rev:
            found.append((url, rev))
    return found


@reader("precommit", is_precommit)
def read_precommit_hooks(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Hook repositories a pre-commit config pins."""
    for url, rev in hook_repositories(parse(text, path.name)):
        repository = repository_of(url)
        if repository is None:
            continue
        line, comment = locate_rev(text, url)
        used = github_ref(repository, rev.strip().strip("'\""), comment, line)
        yield Dep(
            "GitHub",
            used.repo,
            used.version,
            context.source(path, used.line or None),
            used.ref,
            "ci",
            used.note,
            used.moving,
        )
