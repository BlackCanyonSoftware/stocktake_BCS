"""`requirements*.txt` and `constraints*.txt`: a resolved set, usually fully pinned.

The version rule here is the opposite of `pyproject.toml`'s, deliberately. A `pyproject.toml` entry declares a *range*, which says nothing
about what is actually running, so the installed version wins. A requirements file names what *will* be installed, so the pin wins, and the
installed version is consulted only where there is no pin.

The file format is mostly "one requirement per line", with four things that catch a naive reader out: backslash continuations, `--hash=`
digests trailing a requirement, pip options that are not requirements at all (`-r`, `-e`, `--index-url`), and direct references
(`name @ https://...`) where the URL is the version and there is nothing to ask a registry about.

`-r` and `-c` are followed, but only to files the walk would not reach anyway. A project that splits its pins into `requirements/base.txt`
has every one of those files walked on its own account, and following the include as well would report each pin twice. A project that writes
`-r deps/pinned.in` does not, and trial against a real one found a pin in such a file going unreported: nothing said it had been missed,
which is the failure mode this tool is for.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Iterator
from fnmatch import fnmatch
from pathlib import Path

from stocktake.models import Dep
from stocktake.readers.base import Context, UnreadableManifest, logical_lines, read_manifest, reader
from stocktake.readers.pep508 import parse_requirement

FILE_PATTERNS = ("requirements*.txt", "constraints*.txt")

# A requirements file whose name says what it is for: the role is informational, and a filename is the only hint these files give.
# Matched whole, so the plurals have to be listed too.
DEV_WORDS = frozenset({"dev", "develop", "development", "test", "tests", "lint", "lints", "doc", "docs", "ci", "typing"})


def is_requirements_file(path: Path) -> bool:
    return any(fnmatch(path.name, pattern) for pattern in FILE_PATTERNS)


# `-r other.txt`, `--requirement=other.txt`, and the same two for constraints. The target may be quoted, which is how a path with a
# space in it is written, and an unquoted one runs to the first space.
INCLUDE = re.compile(r"""^(?:-r|--requirement|-c|--constraint)[=\s]+(?:"([^"]+)"|'([^']+)'|(\S+))""")


def included_file(line: str, path: Path) -> Path | None:
    """The file a `-r` or `-c` line points at, resolved against the file holding the line, or None when the line is not an include.

    Resolved against the including file's own directory, which is pip's rule and not the project root: `requirements/dev.txt` saying
    `-r base.txt` means `requirements/base.txt`.
    """
    text = re.sub(r"(^|\s)#.*$", "", line).strip()
    match = INCLUDE.match(text)
    if match is None:
        return None
    target = next(group for group in match.groups() if group is not None)
    if target.startswith(("http://", "https://")):
        return None  # pip will fetch it; a reader does not touch the network (docs/adr/0003)
    # Normalised, not resolved: a `-r ../shared.in` has to lose its `..` before the report can name it relative to the project root, and
    # resolving would also follow symlinks, which would make the reported path somewhere the reader never wrote.
    return Path(os.path.normpath(path.parent / target))


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


def _should_follow(included: Path, context: Context, seen: set[Path]) -> bool:
    """Whether an included file is one this reader has to open itself.

    No to a file the walk reaches anyway, or its pins would be reported twice. No to a file outside the project, because the report names
    sources relative to the root and there is no honest way to write a path that is not under it. No to one already followed, which is what
    keeps a pair of files that include each other from recursing forever.
    """
    if is_requirements_file(included) or included in seen:
        return False
    try:
        return included.resolve().is_relative_to(context.root.resolve()) and included.is_file()
    except OSError:
        return False


def _requirements(path: Path, text: str, context: Context, seen: set[Path]) -> Iterator[Dep]:
    role = role_of(path)
    for number, line in logical_lines(text):
        included = included_file(line, path)
        if included is not None:
            if not _should_follow(included, context, seen):
                continue
            seen.add(included)
            try:
                included_text = read_manifest(included)
            except UnreadableManifest as exc:
                # A file named in a `-r` is a file this reader claimed, so failing to read it is reported like any other unreadable manifest.
                # The include resolving quietly to nothing is the case that has to be impossible.
                raise UnreadableManifest(f"includes {included.name}, which {exc.reason}") from exc
            yield from _requirements(included, included_text, context, seen)
            continue
        entry = requirement_in(line)
        if not entry:
            continue
        parsed = parse_requirement(entry)
        if parsed is None:
            continue
        name, pinned, spec = parsed
        yield Dep("PyPI", name, pinned or context.installed(name), context.source(path, number), spec, role)


@reader("python", is_requirements_file)
def read_requirements(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Dependencies listed in a requirements or constraints file, and in any file it includes that the walk would not reach."""
    yield from _requirements(path, text, context, {path})
