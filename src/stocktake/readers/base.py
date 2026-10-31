"""What a reader is: something that turns one kind of file into dependencies.

A reader never touches the network, and nothing outside this package reads a project file (docs/adr/0003). That separation is what lets every
reader be tested with a string and a temporary directory, with no fake network at all.

Adding an ecosystem means a new module beside this one, imported in `__init__.py`, plus a registry client and a guard test. Nothing existing
changes.
"""

from __future__ import annotations

import codecs
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from stocktake.models import Dep

InstalledFn = Callable[[str], str | None]


class UnreadableManifest(Exception):
    """A reader knew which file this was and could not read it.

    Raised, never swallowed. A manifest that cannot be parsed is not an empty manifest, and the difference matters more here than almost
    anywhere: a truncated `package.json` that is quietly skipped turns into a clean report for a project nobody checked.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# Byte-order marks, longest first. UTF-32-LE starts with the two bytes of UTF-16-LE, so testing in this order is not a style choice: the
# other order decodes a UTF-32 file as UTF-16 and produces a file full of NULs that parses as nothing at all.
BYTE_ORDER_MARKS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)


def read_manifest(path: Path) -> str:
    """The text of one manifest, decoded by its byte-order mark where it has one.

    Raises `UnreadableManifest` instead of returning something that merely looks like text. The previous reading used
    `errors="replace"`, which never fails and is exactly the problem: a UTF-16 `requirements.txt` — what PowerShell's `>` writes, so a
    common accident rather than an exotic one — came back as NUL between every character, matched no requirement, and reported a project with
    no dependencies. Of the three ways this went wrong in trial, that one is the worst, because the file is perfectly good and the report said
    there was nothing in it.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise UnreadableManifest(f"could not be opened ({exc.strerror or exc})") from exc

    for mark, encoding in BYTE_ORDER_MARKS:
        if data.startswith(mark):
            try:
                return data[len(mark) :].decode(encoding) if encoding != "utf-8-sig" else data.decode(encoding)
            except UnicodeDecodeError as exc:
                raise UnreadableManifest(f"is marked as {encoding} and is not valid {encoding} (byte {exc.start})") from exc

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnreadableManifest(f"is not text: not valid UTF-8 at byte {exc.start}, and it carries no byte-order mark") from exc

    # UTF-16 and UTF-32 without a byte-order mark are valid UTF-8 as far as the decoder is concerned, and come back as a NUL between every
    # character: no requirement matches, and the file reads as an empty project. No real manifest holds a NUL, so this costs nothing and
    # closes the last way a perfectly good file could be reported as having nothing in it.
    if "\x00" in text:
        raise UnreadableManifest("is not text: it holds NUL bytes, so it is probably UTF-16 or UTF-32 saved without a byte-order mark")
    return text


@dataclass(frozen=True, slots=True)
class Context:
    """Everything a reader may know besides the file in front of it.

    `installed` answers what version of a package is present in this environment, so a reader can report the version actually in use without
    importing `importlib.metadata` itself. That is also what makes the behaviour testable with a dictionary.
    """

    root: Path
    installed: InstalledFn

    def source(self, path: Path, line: int | None = None) -> str:
        """How a finding names where it came from: a path relative to the project root, and a line number when there is one."""
        relative = path.relative_to(self.root).as_posix()
        return f"{relative}:{line}" if line else relative


ReadFn = Callable[[Path, str, Context], Iterable[Dep]]


@dataclass(frozen=True, slots=True)
class Reader:
    """One registered reader: which group of ecosystems it belongs to, which files it wants, and how it reads them."""

    group: str  # the name a project enables in its config: "python", "binaries", "npm", "workflows", "containers"
    interested: Callable[[Path], bool]
    read: ReadFn
    description: str = ""


READERS: list[Reader] = []


def reader(group: str, interested: Callable[[Path], bool], description: str = "") -> Callable[[ReadFn], ReadFn]:
    """Register a reading function. Used as a decorator at the bottom of each reader module."""

    def register(function: ReadFn) -> ReadFn:
        first_line = (function.__doc__ or "").strip().splitlines()
        READERS.append(Reader(group, interested, function, description or (first_line[0] if first_line else function.__name__)))
        return function

    return register


def groups() -> tuple[str, ...]:
    """Every group a project could enable, in registration order."""
    seen = dict.fromkeys(r.group for r in READERS)
    return tuple(seen)


def logical_lines(text: str) -> list[tuple[int, str]]:
    """A file's lines with backslash continuations joined, each paired with the number of its first physical line.

    Shared because Dockerfiles and requirements files both use trailing backslashes, and because the line number has to be where the statement
    *started*: that is what the report points at, not wherever the continuation happened to end.
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
