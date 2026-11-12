"""The edit that would fix a finding, worked out but never made.

StockTake never edits a dependency, with any flag, ever; the furthest it goes is printing the edit it would make (`AGENTS.md`, and the reason
is [ADR 0014](adr/0014-propose-prints-an-edit-and-never-makes-one.md)). This module works one out. It opens project files to read the line a
finding came from, and writes nothing.

The careful part is not "what is the newest version" — `advisories.fix_target` already answers that for a vulnerability. It is that **the
right answer is not always an edit**, and a tool that printed one anyway would be telling people to hand-edit generated files. Three cases:

- **A version written in a hand-kept file** — a `requirements.txt` pin, a Dockerfile `FROM`, a workflow `uses:`, a pre-commit `rev`. Here an
  edit is exactly right, and it is shown as one: the line as it stands and the line as it would be.
- **A lock file.** `package-lock.json`, `pnpm-lock.yaml`, `uv.lock` and the rest are generated. Hand-editing one produces a lock that
  disagrees with itself, so the proposal is the command that regenerates it.
- **A range resolved against what is installed.** A `pyproject.toml` saying `httpx>=0.27` is not wrong when the installed httpx is old; the
  file needs no edit at all and the environment does. The proposal is the upgrade command.

An edit is offered **only when the old version is found exactly once on its line**. Found twice, or not at all, and no edit is printed —
because an edit that is nearly right is worse than a sentence saying what to do, and this is a tool nobody should have to double-check.
"""

from __future__ import annotations

from pathlib import Path

from stocktake.advisories import fix_target, severity_tally
from stocktake.models import COMMAND, EDIT, MANUAL, Finding, Proposal, Report
from stocktake.readers import UnreadableManifest, read_manifest
from stocktake.versions import release_tuple

# What regenerates a lock file, by the name of the lock. Hand-editing any of these is how a lock comes to disagree with itself.
LOCK_COMMANDS: dict[str, str] = {
    "uv.lock": "uv lock --upgrade-package {name}",
    "poetry.lock": "poetry update {name}",
    "pdm.lock": "pdm update {name}",
    "Pipfile.lock": "pipenv update {name}",
    "package-lock.json": "npm install {name}@{target}",
    "pnpm-lock.yaml": "pnpm update {name}@{target}",
}

# What upgrades a package in the environment a range resolved against.
ENVIRONMENT_COMMANDS: dict[str, str] = {
    "PyPI": 'pip install --upgrade "{name}=={target}"',
    "npm": "npm install {name}@{target}",
}


def _why(finding: Finding) -> str:
    """What this upgrade is for, in a few words, so a long list stays skimmable."""
    if finding.status == "vulnerable":
        tally = ", ".join(f"{count} {label}" for label, count in severity_tally(finding.advisories))
        plural = "advisory" if len(finding.advisories) == 1 else "advisories"
        return f"clears {len(finding.advisories)} {plural} ({tally})"
    if finding.status == "yanked":
        return "this release was withdrawn by its author"
    return f"newer release ({finding.update})" if finding.update else "newer release"


def target_version(finding: Finding) -> str | None:
    """The version to move to, or None when there is nothing to propose.

    For a moving tag it is cut back to the precision the project wrote. Somebody tracking `python:3.12` wants `3.15`, not `3.15.2`: the
    shorter tag is the one they are choosing to follow, and the publisher keeps it pointing at the newest of that line
    ([ADR 0008](adr/0008-a-tag-its-publisher-moves-is-a-range.md)).
    """
    if finding.status == "vulnerable":
        target = fix_target(finding.advisories, finding.dep.version or "0", finding.dep.ecosystem)
    elif finding.status in ("yanked", "outdated"):
        target = finding.latest
    else:
        return None
    if target is None or finding.dep.version is None:
        return target

    if finding.dep.moving:
        depth = len(release_tuple(finding.dep.version))
        parts = release_tuple(target)
        if depth and len(parts) > depth:
            return ".".join(str(part) for part in parts[:depth])
    return target


def _link(finding: Finding, target: str) -> str:
    """Somewhere to read what changed. Only where it cannot be wrong.

    No link for a container image: the page depends on which registry it came from. No GitHub *compare* link either, however much more useful
    it would be — the tag text is not recoverable once the registry's `v` prefix has been stripped, and a link that 404s is worse than none.
    """
    dep = finding.dep
    if dep.ecosystem == "PyPI":
        return f"https://pypi.org/project/{dep.name}/{target}/"
    if dep.ecosystem == "npm":
        return f"https://www.npmjs.com/package/{dep.name}/v/{target}"
    if dep.ecosystem == "GitHub":
        return f"https://github.com/{dep.name}/releases"
    return ""


def _where(source: str) -> tuple[str, int]:
    """A `path:line` source split up. Line 0 when the source names no line, as a lock file's does not."""
    path, _, line = source.rpartition(":")
    return (path, int(line)) if path and line.isdigit() else (source, 0)


def _edited_line(raw: str, dep_name: str, spec: str, version: str, target: str) -> tuple[str, str] | None:
    """The line as it stands and as it would be, or None when no exact single replacement can be made.

    The token replaced is the longest one that identifies this dependency on the line: `flask==3.0.0` before `==3.0.0`, so that a second
    package pinned to the same version on the same `RUN pip install` line cannot be hit by mistake.
    """
    if not spec or version not in spec:
        return None  # a range, or a spec with no version in it: there is nothing on the line to rewrite
    new_spec = spec.replace(version, target, 1)
    for token in (f"{dep_name}{spec}", spec):
        if raw.count(token) == 1:
            return raw.rstrip("\n"), raw.rstrip("\n").replace(token, token.replace(spec, new_spec, 1), 1)
    return None


def _for_finding(finding: Finding, root: Path, lines: dict[str, list[str]]) -> Proposal | None:
    dep = finding.dep
    target = target_version(finding)
    if target is None:
        if finding.status == "vulnerable":
            # Worth saying out loud: there is a known problem and no published fix, which is a decision for a person.
            return Proposal(finding, "", _why(finding), MANUAL, note="no fixed version is named by any of its advisories")
        return None
    if dep.version is None or target == dep.version:
        return None

    path, line = _where(dep.source)
    reason, link = _why(finding), _link(finding, target)
    name = Path(path).name

    if name in LOCK_COMMANDS:
        command = LOCK_COMMANDS[name].format(name=dep.name, target=target)
        return Proposal(finding, target, reason, COMMAND, path, line, command=command, link=link, note="a lock file is generated")

    raw = _line(lines, root, path, line)
    edit = _edited_line(raw, dep.name, dep.spec, dep.version, target) if raw else None
    if edit is not None:
        return Proposal(finding, target, reason, EDIT, path, line, before=edit[0], after=edit[1], link=link)

    # Nothing to rewrite on the line: the file declares a range and the version came from the environment.
    command = ENVIRONMENT_COMMANDS.get(dep.ecosystem, "")
    if command:
        return Proposal(
            finding,
            target,
            reason,
            COMMAND,
            path,
            line,
            command=command.format(name=dep.name, target=target),
            link=link,
            note=f"`{path}` declares a range; it is the installed version that is behind",
        )
    return Proposal(finding, target, reason, MANUAL, path, line, link=link, note="no exact edit could be worked out for this line")


def _line(lines: dict[str, list[str]], root: Path, path: str, number: int) -> str:
    """One line of a project file, read once per file and remembered. Empty when there is no such line."""
    if number <= 0:
        return ""
    if path not in lines:
        try:
            lines[path] = read_manifest(root / path).splitlines()
        except (UnreadableManifest, OSError):
            lines[path] = []
    found = lines[path]
    return found[number - 1] if 0 < number <= len(found) else ""


def proposals(report: Report, root: Path, shown: frozenset[str] | None = None) -> list[Proposal]:
    """What to do about every actionable finding, worst first.

    `shown` narrows it the way `--only` narrows every other format. Nothing is written, now or ever.
    """
    lines: dict[str, list[str]] = {}
    found = []
    for finding in sorted(report.findings, key=lambda f: (f.severity != "fail", -f.rank, f.dep.source, f.dep.name)):
        if shown is not None and finding.status not in shown:
            continue
        proposal = _for_finding(finding, root, lines)
        if proposal is not None:
            found.append(proposal)
    return found
