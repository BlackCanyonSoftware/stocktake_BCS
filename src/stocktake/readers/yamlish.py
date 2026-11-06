"""Enough YAML to read a manifest, and a refusal for everything else.

Several dependency files are YAML — pre-commit hook pins today, `pnpm-lock.yaml` and compose files later — and StockTake has no runtime
dependencies and is not getting one ([ADR 0013](adr/0013-a-strict-yaml-subset-rather-than-a-dependency.md)). So this reads the part of YAML
those files actually use and **raises on the rest** rather than guessing.

The refusal is the whole design. The roadmap's objection to doing this at all was that a half-parser is the "misses things silently" failure
the guard tests exist to catch, and that was right when it was written: there was nowhere for "I could not read this" to go. There is now.
[ADR 0009](adr/0009-an-unread-file-makes-the-run-incomplete.md) made an unreadable manifest fail the run with exit 2, so a parser that stops
at the edge of what it understands is loud, not silent. That is what makes a subset safe, and it is why every unsupported construct below
raises instead of being skipped.

What it reads: comments, block mappings, block sequences, plain and quoted scalars, flow collections, and block scalars (`|`, `>`).
What it refuses: anchors (`&`), aliases (`*`), tags (`!`), merge keys (`<<`), more than one document, and a tab used as indentation.

**Structure is parsed; leaf values are kept as text.** A version is a string, and nothing here needs to know that `[--fix=lf]` is a list or
that `'9.0'` is a number. Not parsing what nothing reads is the difference between this and a YAML library, and it is most of why this is
small enough to be worth trusting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from stocktake.readers.base import UnreadableManifest

# A value that begins with one of these means something this does not implement, and misreading it would be worse than refusing it.
REFUSED = {
    "&": "uses a YAML anchor",
    "*": "uses a YAML alias",
    "!": "uses a YAML tag",
}

# `key:` or `key: value`, where the key is plain or quoted. A `:` inside a plain value (a URL) is not a key separator, which is why the key
# is matched rather than the line being split on the first colon.
KEY = re.compile(r"""^(?P<key>"[^"]*"|'[^']*'|[^\s:#][^:#]*?)\s*:(?:\s+(?P<value>.*))?\s*$""")
ITEM = re.compile(r"^-(?:\s+(?P<value>.*))?\s*$")
BLOCK_SCALAR = re.compile(r"^[|>][0-9+-]*$")


@dataclass(frozen=True, slots=True)
class Line:
    number: int
    indent: int
    text: str


def _strip_comment(text: str) -> str:
    """A `#` starts a comment only when it follows whitespace and is outside quotes, which is YAML's own rule.

    It matters here: `exclude: ^(a|b)` and an entry holding a shell command both contain characters that a looser rule would cut at.
    """
    quote = ""
    for index, character in enumerate(text):
        if quote:
            if character == quote:
                quote = ""
        elif character in "\"'":
            quote = character
        elif character == "#" and (index == 0 or text[index - 1].isspace()):
            return text[:index]
    return text


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _lines(text: str, where: str) -> list[Line]:
    """Every line that carries content, with its indentation, and a refusal for anything this cannot read line-by-line."""
    found: list[Line] = []
    started = False
    for number, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise UnreadableManifest(f"{where}uses a tab to indent line {number}, which YAML does not allow")
        body = _strip_comment(raw).rstrip()
        if not body.strip():
            continue
        if body.strip() in ("---", "..."):
            # One document is all any manifest here needs, and a second would silently replace the first.
            if started:
                raise UnreadableManifest(f"{where}holds more than one YAML document (line {number})")
            continue
        started = True
        found.append(Line(number, len(body) - len(body.lstrip()), body.strip()))
    return found


class _Reader:
    def __init__(self, lines: list[Line], raw: list[str], where: str) -> None:
        self.lines = lines
        self.raw = raw
        self.where = where
        self.at = 0

    def _refuse(self, line: Line, why: str) -> UnreadableManifest:
        return UnreadableManifest(f"{self.where}{why} at line {line.number}, which StockTake's YAML reader does not implement")

    def _value(self, line: Line, text: str) -> Any:
        """A leaf, or the nested block that follows when the leaf is empty."""
        text = text.strip()
        if text and text[0] in REFUSED:
            raise self._refuse(line, REFUSED[text[0]])
        if BLOCK_SCALAR.match(text):
            return self._block_scalar(line)
        if text:
            return _unquote(text)
        # Nothing after the colon: either a nested block indented further, or an empty value.
        if self.at < len(self.lines) and self.lines[self.at].indent > line.indent:
            return self.parse(self.lines[self.at].indent)
        return ""

    def _block_scalar(self, line: Line) -> str:
        """The indented lines under a `|` or `>`, joined.

        Consumed rather than skipped: a folded scalar holding a shell command is in one of the real files this was written for, and a reader
        that did not know where it ended would read its continuation lines as structure.
        """
        collected: list[str] = []
        while self.at < len(self.lines) and self.lines[self.at].indent > line.indent:
            collected.append(self.lines[self.at].text)
            self.at += 1
        return " ".join(collected)

    def parse(self, indent: int) -> Any:
        """Everything at this indentation: a mapping, a sequence, or a single scalar."""
        if self.at >= len(self.lines):
            return ""
        return self._sequence(indent) if ITEM.match(self.lines[self.at].text) else self._mapping(indent)

    def _sequence(self, indent: int) -> list[Any]:
        items: list[Any] = []
        while self.at < len(self.lines) and self.lines[self.at].indent == indent:
            line = self.lines[self.at]
            match = ITEM.match(line.text)
            if match is None:
                break
            self.at += 1
            inside = (match.group("value") or "").strip()
            if not inside:
                items.append(self.parse(self.lines[self.at].indent) if self.at < len(self.lines) else "")
            elif (opening := KEY.match(inside)) is not None:
                # `- key: value` opens a mapping whose first key sits on the dash's own line.
                items.append(self._inline_mapping(line, inside, opening))
            else:
                items.append(self._value(line, inside))
        return items

    def _inline_mapping(self, dash: Line, first: str, match: re.Match[str]) -> dict[str, Any]:
        """A mapping begun on a `-` line. Its later keys are indented to where that first key started.

        The match is handed in rather than recomputed: the caller had to make it to know this was a mapping at all, and re-deriving it here
        would need an `assert` to satisfy the type checker -- which `python -O` removes, turning a type error into a crash.
        """
        inner = dash.indent + (len(dash.text) - len(dash.text[1:].lstrip()))
        found: dict[str, Any] = {_unquote(match.group("key")): self._value(Line(dash.number, inner, first), match.group("value") or "")}
        found.update(self._mapping(inner) if self.at < len(self.lines) and self.lines[self.at].indent == inner else {})
        return found

    def _mapping(self, indent: int) -> dict[str, Any]:
        found: dict[str, Any] = {}
        while self.at < len(self.lines) and self.lines[self.at].indent == indent:
            line = self.lines[self.at]
            if line.text.startswith("<<"):
                raise self._refuse(line, "uses a YAML merge key")
            match = KEY.match(line.text)
            if match is None:
                break
            self.at += 1
            found[_unquote(match.group("key"))] = self._value(line, match.group("value") or "")
        return found


def parse(text: str, where: str = "") -> Any:
    """One YAML document, as far as this reads YAML. Raises `UnreadableManifest` at the first thing it does not implement."""
    prefix = f"{where}: " if where else ""
    lines = _lines(text, prefix)
    if not lines:
        return {}
    reader = _Reader(lines, text.splitlines(), prefix)
    parsed = reader.parse(lines[0].indent)
    if reader.at < len(reader.lines):
        stuck = reader.lines[reader.at]
        raise UnreadableManifest(f"{prefix}could not be read past line {stuck.number} ({stuck.text[:40]!r})")
    return parsed
