"""Container base images: the `FROM` line of a Dockerfile.

The pins that were invisible. A Dockerfile has been read since the first milestone — for its `pip install` lines and the binaries it
downloads — and its `FROM` was passed over without a word, so a project running on a base image three releases behind was told nothing, and
nothing in the report said a line had been skipped. That is not an unread *file*, which the report has always named; it is a silent gap
inside a file that is read, which is worse, because there is no gap to see.

Three things make this harder than matching `FROM`:

- **A stage is not an image.** `FROM builder` in a multi-stage build names an earlier `FROM ... AS builder`, and asking a registry about a
  package called `builder` would produce a confident `unknown` about something that was never a dependency.
- **A tag is not a version.** `python:3.12-slim` names a variant as well; `debian:bookworm-slim` names a Debian release and no version at
  all; `latest` names nothing. Only the first can be compared, and only against other `-slim` tags (docs/adr/0012).
- **The version is often a build argument.** `ARG PYTHON=3.12` then `FROM python:${PYTHON}-slim`, which is the same substitution problem the
  release-download reader already solves in this folder.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from stocktake.models import Dep
from stocktake.readers.base import Context, logical_lines, reader
from stocktake.readers.dockerfile import is_dockerfile
from stocktake.versions import container_tag

# `FROM [--platform=...] image[:tag][@digest] [AS stage]`
FROM_LINE = re.compile(
    r"^\s*FROM\s+(?:--\S+\s+)*(?P<image>\S+)(?:\s+(?i:AS)\s+(?P<stage>\S+))?\s*$",
    re.IGNORECASE,
)
ARG_LINE = re.compile(r"^\s*(?:ARG|ENV)\s+(?P<name>\w+)\s*=\s*(?P<value>\S+)", re.IGNORECASE)
VARIABLE = re.compile(r"\$\{?(\w+)(?::-([^}]*))?\}?")

# `FROM scratch` is the empty image: there is no registry entry for it and never will be.
NOT_AN_IMAGE = frozenset({"scratch"})

NO_TAG_NOTE = "no tag is pinned, so the image is whatever `latest` points at when it is built"
DIGEST_NOTE = "pinned to a digest, which fixes the image exactly and names no version to compare"
UNVERSIONED_NOTE = "the tag `{tag}` names a release channel rather than a version, so there is nothing to compare it against"
UNRESOLVED_NOTE = "the tag is a build argument this file does not give a default for, so there is no version to compare"


def substitute(text: str, values: dict[str, str]) -> str:
    """`${PYTHON_VERSION}` replaced by what an earlier ARG or ENV set it to, falling back to a `:-default` where the line gives one."""

    def replace(match: re.Match[str]) -> str:
        return values.get(match.group(1), match.group(2) if match.group(2) is not None else match.group(0))

    return VARIABLE.sub(replace, text)


def split_image(image: str) -> tuple[str, str, str]:
    """An image reference into (repository, tag, digest). Tag and digest are empty when absent."""
    rest, _, digest = image.partition("@")
    head, separator, tail = rest.rpartition(":")
    # A `:` before a `/` is a registry's port, not a tag: `localhost:5000/thing` has no tag.
    return (head, tail, digest) if separator and "/" not in tail else (rest, "", digest)


def _named(image: str, variant: str) -> str:
    """What this dependency is called: the image, plus its variant when it has one, so two variants are two things to ask about."""
    return f"{image}:{variant}" if variant else image


def base_images(text: str) -> Iterator[tuple[int, str, str, str]]:
    """Every `FROM` that names a real image, as (line, repository, tag, digest), with build arguments already substituted.

    Stage names are collected as they are declared so that a later `FROM` referring to one is skipped rather than asked about.
    """
    values: dict[str, str] = {}
    stages: set[str] = set()
    for number, line in logical_lines(text):
        argument = ARG_LINE.match(line)
        if argument:
            values[argument.group("name")] = argument.group("value").strip("\"'")
            continue

        match = FROM_LINE.match(line)
        if not match:
            continue
        if match.group("stage"):
            stages.add(match.group("stage").lower())

        image, tag, digest = split_image(substitute(match.group("image"), values).strip("\"'"))
        if image.lower() in stages or image.lower() in NOT_AN_IMAGE:
            continue
        yield number, image, tag, digest


@reader("containers", is_dockerfile)
def read_base_images(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Base images a Dockerfile builds on."""
    for number, image, tag, digest in base_images(text):
        source = context.source(path, number)
        if not tag:
            note = DIGEST_NOTE if digest else NO_TAG_NOTE
            yield Dep("Docker", image, None, source, digest or "latest", "image", note)
            continue

        parts = container_tag(tag)
        if parts is None:
            # A codename, `latest`, or a variable nothing defined. Named with the tag, because `debian (none)` does not say which line to go
            # and look at, and two Dockerfiles on different channels of one image are two different things to report.
            note = UNRESOLVED_NOTE if "$" in tag else UNVERSIONED_NOTE.format(tag=tag)
            yield Dep("Docker", _named(image, tag), None, source, tag, "image", note)
            continue

        version, variant = parts
        # `moving=True`: `python:3.12` already points at the newest 3.12.x, so only a change at the precision written down is an update
        # (docs/adr/0008). A digest beside the tag fixes the image exactly, so that one is not moving.
        yield Dep("Docker", _named(image, variant), version, source, tag, "image", "", moving=not digest)
