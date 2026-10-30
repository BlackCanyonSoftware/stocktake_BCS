"""`requirements*.txt` and `constraints*.txt`: a resolved set, usually fully pinned.

The version rule here is the opposite of `pyproject.toml`'s, deliberately. A `pyproject.toml` entry declares a *range*, which says nothing
about what is actually running, so the installed version wins. A requirements file names what *will* be installed, so the pin wins, and the
installed version is consulted only where there is no pin.

The file format is mostly "one requirement per line", with four things that catch a naive reader out: backslash continuations, `--hash=`
digests trailing a requirement, pip options that are not requirements at all (`-r`, `-e`, `--index-url`), and direct references
(`name @ https://...`) where the URL is the version and there is nothing to ask a registry about.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from fnmatch import fnmatch
from pathlib import Path

from stocktake.models import Dep
from stocktake.readers.base import Context, logical_lines, reader
from stocktake.readers.pep508 import parse_requirement

FILE_PATTERNS = ("requirements*.txt", "constraints*.txt")

# A requirements file whose name says what it is for: the role is informational, and a filename is the only hint these files give.
# Matched whole, so the plurals have to be listed too.
DEV_WORDS = frozenset({"dev", "develop", "development", "test", "tests", "lint", "lints", "doc", "docs", "ci", "typing"})


def is_requirements_file(path: Path) -> bool:
    return any(fnmatch(path.name, pattern) for pattern in FILE_PATTERNS)


def requirement_in(line: str) -> str:
    """The requirement a line holds, or an empty string when it holds something else."""
    text = re.sub(r"(^|\s)#.*$", "", line).strip()
    if not text or text.startswith("-"):
        return ""  # a pip option. Where it points at another file, that file is walked on its own account.
    if " @ " in text or text.startswith(("http://", "https://", "git+", "file:")):
        return ""  # a direct reference: the URL fixes it, and no registry can be asked about it
    return text.split("--hash")[0].strip()


def role_of(path: Path) -> str:
    """`dev` when the filename says so, else `runtime`. A guess, but the only information the format offers.

    Matched as whole words, not substrings: `requirements-social.txt` contains "ci" and is not a CI requirements file.
    """
    words = re.split(r"[^a-z0-9]+", path.stem.lower())
    return "dev" if any(word in DEV_WORDS for word in words) else "runtime"


@reader("python", is_requirements_file)
def read_requirements(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Dependencies listed in a requirements or constraints file."""
    role = role_of(path)
    for number, line in logical_lines(text):
        entry = requirement_in(line)
        if not entry:
            continue
        parsed = parse_requirement(entry)
        if parsed is None:
            continue
        name, pinned, spec = parsed
        yield Dep("PyPI", name, pinned or context.installed(name), context.source(path, number), spec, role)
