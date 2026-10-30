"""Dockerfiles: the pins no hosted dependency bot can see.

A `RUN pip install name==1.2.3` line is a dependency as surely as anything in a manifest, and it is invisible to Dependabot and Renovate. The
same goes for a binary fetched from a GitHub release. Both are read here, from the same files, by two separate readers, because a project may
well want the Python pins checked and not care about release binaries.

The two things that make this harder than a regular expression: a shell line may be continued across several physical lines with backslashes,
and a release URL usually names its version through a shell variable assigned earlier in the file.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Iterator
from pathlib import Path

from stocktake.models import Dep
from stocktake.readers.base import Context, reader
from stocktake.readers.pep508 import parse_requirement

# pip options that swallow the next token, which would otherwise be mistaken for a package name.
OPTIONS_WITH_ARGUMENT = frozenset(
    {
        "-r",
        "-c",
        "-e",
        "-i",
        "-f",
        "-t",
        "--requirement",
        "--constraint",
        "--editable",
        "--index-url",
        "--extra-index-url",
        "--find-links",
        "--target",
        "--prefix",
        "--root",
        "--platform",
        "--python-version",
        "--implementation",
        "--abi",
        "--only-binary",
        "--no-binary",
        "--config-settings",
    }
)

INSTALLERS = re.compile(r"\b(?:pip\d?|uv\s+pip|uv\s+tool|pipx)\s+install\b")
RELEASE_DOWNLOAD = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/releases/download/([^/\s\"']+)/")


def is_dockerfile(path: Path) -> bool:
    name = path.name
    return name in {"Dockerfile", "Containerfile"} or name.startswith("Dockerfile.") or name.endswith(".Dockerfile")


def logical_lines(text: str) -> list[tuple[int, str]]:
    """The file's lines with backslash continuations joined, each paired with the number of its first physical line.

    The line number matters: it is what the report points at, so it has to be where the `RUN` started, not where it happened to end.
    """
    joined: list[tuple[int, str]] = []
    buffer = ""
    start = 0
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not buffer:
            start = number
        if line.endswith("\\"):
            buffer += line[:-1] + " "
            continue
        buffer += line
        joined.append((start, buffer))
        buffer = ""
    if buffer:
        joined.append((start, buffer))
    return joined


def pip_requirements(command: str) -> list[tuple[str, str | None, str]]:
    """Every package a shell line hands to an installer, as (name, pinned version or None, specifier as written).

    Covers `pip install`, `uv pip install`, `uv tool install` and `pipx install`. A name with no `==` is reported with no version, because an
    unpinned install is a finding in its own right rather than something to skip.
    """
    found: list[tuple[str, str | None, str]] = []
    for segment in re.split(r"&&|\|\||;|\|", command):
        if not INSTALLERS.search(segment):
            continue
        try:
            tokens = shlex.split(segment.split("install", 1)[1], comments=True)
        except ValueError:  # an unbalanced quote: nothing reliable to read here
            continue
        skip_next = False
        for token in tokens:
            if skip_next:
                skip_next = False
                continue
            if token in OPTIONS_WITH_ARGUMENT:
                skip_next = True
                continue
            # Flags, local paths, VCS and URL installs, and anything with a shell variable in it: not a registry package name.
            if token.startswith(("-", ".", "/", "git+", "http")) or "$" in token or "/" in token:
                continue
            parsed = parse_requirement(token)
            if parsed is not None:
                found.append(parsed)
    return found


def github_downloads(text: str) -> list[tuple[str, str, int]]:
    """Every GitHub release binary the file downloads, as (owner/repo, version, line).

    The tag is usually a shell variable, so it is resolved against the nearest earlier assignment of that name. `v0.0.0` is skipped: projects
    park model files and other assets under it, and treating it as a release produced a false "major update available" in the original.
    """
    found: list[tuple[str, str, int]] = []
    for match in RELEASE_DOWNLOAD.finditer(text):
        repo, tag = match.group(1), match.group(2)
        for variable in re.findall(r"\$\{?(\w+?)(?:#v)?\}?(?=\W|$)", tag):
            assignments = list(re.finditer(rf"(?<!\w){variable}=[\"']?v?([0-9][\w.]*)", text[: match.start()]))
            if assignments:
                tag = re.sub(rf"\$\{{?{variable}[^}}]*\}}?", assignments[-1].group(1), tag)
        version = tag.removeprefix("v")
        if re.match(r"\d", version) and version != "0.0.0":
            found.append((repo, version, text[: match.start()].count("\n") + 1))
    return found


def _run_lines(text: str) -> Iterator[tuple[int, str]]:
    for number, line in logical_lines(text):
        if re.match(r"\s*RUN\b", line):
            yield number, line


@reader("python", is_dockerfile)
def read_pip_pins(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Python packages installed by a RUN line in a Dockerfile."""
    for number, line in _run_lines(text):
        for name, version, spec in pip_requirements(line):
            yield Dep("PyPI", name, version, context.source(path, number), spec, "image")


@reader("binaries", is_dockerfile)
def read_release_downloads(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Binaries downloaded from a GitHub release by a Dockerfile."""
    for repo, version, number in github_downloads(text):
        yield Dep("GitHub", repo, version, context.source(path, number), f"=={version}", "image")
