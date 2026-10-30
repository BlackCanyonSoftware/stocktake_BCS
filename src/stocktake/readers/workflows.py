"""GitHub Actions: the versions a workflow pins.

`uses: owner/repo@ref` is a dependency on somebody else's code, running inside the repository with access to its secrets, and it is invisible
to everything that reads package manifests. It is also the one kind of dependency people routinely pin to a commit SHA — which is the right
thing to do and makes the version unreadable. So where the line carries the conventional version comment beside the SHA, that is used:

    uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8  # v5.0.0

A ref that names no version at all is reported with the reason, never silently dropped. An action tracking `@main` and an action pinned to a
commit are both uncheckable, but for opposite reasons, and the report says which.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from stocktake.models import Dep
from stocktake.readers.base import Context, reader

USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<value>.+)$")
VERSION_REF = re.compile(r"^v?\d+(?:\.\d+)*$")
COMMIT_REF = re.compile(r"^[0-9a-f]{40}$")
VERSION_IN_COMMENT = re.compile(r"\bv?(\d+(?:\.\d+)*)\b")

# Referring to the repository's own code, or to a container, rather than to a published action.
LOCAL_OR_CONTAINER = ("./", ".\\", "../", "docker://")

COMMIT_NOTE = "pinned to a commit, which cannot be compared with a release; name the version in a comment (`# v5.0.0`) and it will be"
MOVING_NOTE = "tracks a branch or a named ref, so which code runs depends on when the workflow runs"


def is_workflow(path: Path) -> bool:
    """A GitHub Actions workflow, or an action definition — both of which pin other actions."""
    if path.suffix not in (".yml", ".yaml"):
        return False
    if path.stem == "action":
        return True
    return path.parent.name == "workflows" and path.parent.parent.name == ".github"


@dataclass(frozen=True, slots=True)
class Used:
    """One `uses:` reference, and what could be made of its ref."""

    repo: str
    ref: str
    line: int
    version: str | None = None
    note: str = ""
    moving: bool = False


def workflow_uses(text: str) -> list[Used]:
    """Every action the file uses, with the ref read as far as it can be."""
    found = []
    for number, raw in enumerate(text.splitlines(), 1):
        match = USES_LINE.match(raw)
        if not match:
            continue
        value, _, comment = match.group("value").partition("#")
        value = value.strip().strip("'\"")
        if not value or value.startswith(LOCAL_OR_CONTAINER):
            continue
        target, separator, ref = value.partition("@")
        segments = target.split("/")
        if not separator or not ref.strip() or len(segments) < 2:
            continue  # no ref at all, or not an owner/repo reference
        found.append(_read_ref("/".join(segments[:2]), ref.strip(), comment, number))
    return found


def _read_ref(repo: str, ref: str, comment: str, line: int) -> Used:
    if VERSION_REF.match(ref):
        version = ref.removeprefix("v")
        # `@v7` and `@v7.1` are tags GitHub advances as it releases; `@v7.1.0` is one by convention nobody moves.
        return Used(repo, ref, line, version, moving=version.count(".") < 2)
    if COMMIT_REF.match(ref):
        hint = VERSION_IN_COMMENT.search(comment)
        return Used(repo, ref, line, hint.group(1)) if hint else Used(repo, ref, line, note=COMMIT_NOTE)
    return Used(repo, ref, line, note=MOVING_NOTE)


@reader("workflows", is_workflow)
def read_workflow_actions(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Actions a GitHub Actions workflow pins."""
    for used in workflow_uses(text):
        yield Dep(
            "GitHub",
            used.repo,
            used.version,
            context.source(path, used.line),
            f"@{used.ref}",
            "ci",
            used.note,
            used.moving,
        )
