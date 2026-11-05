"""Reading `FROM` lines: the base-image pins that were invisible.

A Dockerfile has been read since the first milestone, for its `pip install` lines and the binaries it downloads, and its `FROM` was passed
over without a word. That is not an unread *file* — the report has always named those — it is a silent gap inside a file that is read, which
is worse, because there is nothing to see.

The last test is the guard: it counts the `FROM` lines with a plain regular expression, independently of the reader, and fails if the two
disagree.
"""

import re

import pytest

from stocktake.readers.base import Context
from stocktake.readers.containers import read_base_images, split_image, substitute

DOCKERFILE = """# A realistic multi-stage build
ARG PYTHON_VERSION=3.12
ARG NODE=20-alpine

FROM python:${PYTHON_VERSION}-slim AS builder
RUN pip install build==1.2.1

FROM node:${NODE} AS assets
RUN npm ci

FROM builder AS tester
RUN pytest

FROM scratch AS empty
COPY --from=builder /app /app

FROM --platform=$BUILDPLATFORM ghcr.io/owner/tool:1.17.0
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
FROM debian:bookworm-slim
FROM redis@sha256:aaaabbbbccccddddeeeeffff0000111122223333444455556666777788889999
FROM ubuntu
"""


def read(tmp_path, text=DOCKERFILE):
    path = tmp_path / "Dockerfile"
    path.write_text(text, encoding="utf-8")
    return list(read_base_images(path, text, Context(root=tmp_path, installed=lambda name: None)))


# ---------- what is and is not an image ----------
def test_a_stage_name_is_not_an_image(tmp_path):
    """`FROM builder` names an earlier stage. Asking a registry about a package called `builder` would produce a confident `unknown`."""
    assert "builder" not in {d.name for d in read(tmp_path)}


def test_scratch_is_not_an_image(tmp_path):
    assert "scratch" not in {d.name for d in read(tmp_path)}


def test_a_platform_flag_does_not_hide_the_image(tmp_path):
    assert "ghcr.io/owner/tool" in {d.name for d in read(tmp_path)}


# ---------- tags ----------
def test_a_variant_is_part_of_what_is_asked_about(tmp_path):
    """`python:3.12-slim` is the slim variant at 3.12. The newest tag of `python` is some other variant, and recommending it would be
    telling somebody on `-slim` to move to an image that is not slim."""
    found = {d.name: d for d in read(tmp_path)}
    assert found["python:slim"].version == "3.12"
    assert found["python:slim"].moving is True


def test_a_build_argument_is_resolved(tmp_path):
    found = {d.name: d.version for d in read(tmp_path)}
    assert found["python:slim"] == "3.12"
    assert found["node:alpine"] == "20"


def test_a_registry_host_is_kept_and_a_version_tag_is_pinned(tmp_path):
    found = {d.name: d for d in read(tmp_path)}
    assert found["ghcr.io/owner/tool"].version == "1.17.0"
    assert found["mcr.microsoft.com/playwright/python:jammy"].version == "1.47.0"


def test_a_codename_tag_is_reported_with_the_reason_rather_than_compared(tmp_path):
    """A Debian release name has no ordering to put it in. Comparing it as a version is how a tool invents an upgrade nobody can make."""
    found = {d.name: d for d in read(tmp_path)}
    assert found["debian:bookworm-slim"].version is None
    assert "names a release channel" in found["debian:bookworm-slim"].note


def test_a_digest_pin_is_named_as_one(tmp_path):
    found = {d.name: d for d in read(tmp_path)}
    assert found["redis"].version is None
    assert "digest" in found["redis"].note


def test_an_image_with_no_tag_says_so(tmp_path):
    found = {d.name: d for d in read(tmp_path)}
    assert found["ubuntu"].version is None
    assert "latest" in found["ubuntu"].note


def test_every_finding_is_an_image_of_this_file(tmp_path):
    for dep in read(tmp_path):
        assert dep.ecosystem == "Docker"
        assert dep.role == "image"
        assert dep.source.startswith("Dockerfile:")


# ---------- the pieces ----------
@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("python:3.12", ("python", "3.12", "")),
        ("python", ("python", "", "")),
        ("ghcr.io/owner/tool:1.0", ("ghcr.io/owner/tool", "1.0", "")),
        ("localhost:5000/thing", ("localhost:5000/thing", "", "")),
        ("localhost:5000/thing:2.0", ("localhost:5000/thing", "2.0", "")),
        ("redis@sha256:abc", ("redis", "", "sha256:abc")),
        ("redis:7@sha256:abc", ("redis", "7", "sha256:abc")),
    ],
)
def test_an_image_reference_is_split_into_its_parts(image, expected):
    """A `:` before a `/` is a registry's port, not a tag."""
    assert split_image(image) == expected


def test_a_variable_falls_back_to_the_default_written_beside_it():
    assert substitute("${TAG:-3.12}", {}) == "3.12"
    assert substitute("${TAG:-3.12}", {"TAG": "3.13"}) == "3.13"


def test_a_variable_nothing_defined_is_left_alone_rather_than_guessed_at(tmp_path):
    text = "FROM python:${UNSET_SOMEWHERE}\n"
    (dep,) = read(tmp_path, text)
    assert dep.version is None
    assert "build argument" in dep.note


# ---------- the guard ----------
def test_no_base_image_in_the_file_escapes_the_reader(tmp_path):
    """Counts the FROM lines with an independent regular expression and insists the reader agrees.

    Stage names and `scratch` are excluded here by the same reasoning the reader uses, but worked out separately: the point of a guard is
    that it would still fail if the reader's own logic were wrong.
    """
    stages = {m.group(1).lower() for m in re.finditer(r"(?im)^\s*FROM\s+.*?\s+AS\s+(\S+)\s*$", DOCKERFILE)}
    expected = set()
    for match in re.finditer(r"(?im)^\s*FROM\s+(?:--\S+\s+)*(\S+)", DOCKERFILE):
        reference = match.group(1)
        bare = reference.partition("@")[0].partition(":")[0]
        if bare.lower() in stages or bare.lower() == "scratch" or reference.startswith("$"):
            continue
        expected.add(bare)

    found = {d.name.rpartition(":")[0] if ":" in d.name and "/" not in d.name.rpartition(":")[2] else d.name for d in read(tmp_path)}
    assert expected == found, f"the reader and an independent count disagree about: {expected ^ found}"
