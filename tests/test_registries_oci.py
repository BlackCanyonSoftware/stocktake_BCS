"""Asking a container registry for the tags of an image.

The first client here that needs a credential to read something entirely public, so the handshake is most of what is tested: ask, and if the
answer is "not without a token", get one and ask again. The rest is the rule that only tags of the same variant are ever compared.
"""

import pytest

from stocktake.registries.http import Cache, Unauthorized
from stocktake.registries.oci import DOCKER_HUB, OCI, split_reference, split_variant

PYTHON_TAGS = ["3.11", "3.11-slim", "3.12", "3.12-slim", "3.13", "3.13-slim", "3.14-rc", "latest", "bookworm", "slim-bullseye"]


class FakeRegistry:
    """A registry that answers tag listings, and can insist on a token first.

    `calls` records every URL, which is how a test asserts that a token was asked for once and only when it was needed.
    """

    def __init__(self, tags=None, needs_token=False, token="t0ken"):  # noqa: S107  (a fake token for a fake registry)
        self.tags = tags if tags is not None else {"library/python": PYTHON_TAGS}
        self.needs_token = needs_token
        self.token = token
        self.calls: list[tuple[str, bool]] = []

    def __call__(self, url, body=None, headers=None):
        self.calls.append((url, bool(headers)))
        if "/token" in url:
            return {"token": self.token}
        repository = url.split("/v2/", 1)[1].rsplit("/tags/list", 1)[0]
        if self.needs_token and not headers:
            raise Unauthorized(f"{url} answered 401")
        if repository not in self.tags:
            return None
        return {"name": repository, "tags": self.tags[repository]}


def client(tmp_path, net, **kwargs):
    return OCI(Cache(fetch=net, path=tmp_path / "cache.json", now=lambda: 1000.0, **kwargs))


# ---------- the handshake ----------
def test_a_registry_that_answers_without_a_token_is_never_asked_for_one(tmp_path):
    net = FakeRegistry(needs_token=False)
    assert client(tmp_path, net).latest("python:slim") is not None
    assert not any("/token" in url for url, _ in net.calls), "a registry that does not need a token should not be asked for one"


def test_a_registry_that_refuses_is_asked_again_with_a_token(tmp_path):
    net = FakeRegistry(needs_token=True)
    assert client(tmp_path, net).latest("python:slim").latest == "3.13"
    urls = [url for url, _ in net.calls]
    assert sum("/token" in url for url in urls) == 1, "exactly one token, fetched only after being told one was needed"
    assert net.calls[-1][1] is True, "the retry carries the token"


def test_the_token_is_never_written_to_the_cache(tmp_path):
    """An OCI token is good for minutes and this cache keeps answers for hours, so a cached one would be an expired one for most of its
    life, and every run after the first would fail with a 401 that looks like a broken registry."""
    net = FakeRegistry(needs_token=True)
    cache = Cache(fetch=net, path=tmp_path / "cache.json", now=lambda: 1000.0)
    OCI(cache).latest("python:slim")
    cache.flush()
    assert not any("/token" in key for key in cache.entries), "a credential has no business in a cache shared across projects"
    assert any("tags/list" in key for key in cache.entries), "the tag listing itself is worth keeping"


def test_a_registry_that_will_not_issue_a_token_is_unknown_rather_than_absent(tmp_path):
    """None means "no such image", which would be a lie about a private one. Raising makes it `unknown` with the reason."""

    def net(url, body=None, headers=None):
        if "/token" in url:
            return {}
        raise Unauthorized(f"{url} answered 401")

    with pytest.raises(Unauthorized):
        client(tmp_path, net).latest("private/thing")


# ---------- which tag is the answer ----------
def test_only_tags_of_the_same_variant_are_compared(tmp_path):
    found = client(tmp_path, FakeRegistry())
    assert found.latest("python:slim").latest == "3.13", "never 3.14-rc, which is not slim"
    assert found.latest("python").latest == "3.13", "never 3.13-slim, which is not plain"


def test_a_prerelease_variant_is_its_own_variant(tmp_path):
    assert client(tmp_path, FakeRegistry()).latest("python:rc").latest == "3.14"


def test_tags_that_name_no_version_are_ignored(tmp_path):
    """`latest`, `bookworm` and `slim-bullseye` are in the listing and none of them is an answer to "what is the newest 3.x"."""
    assert client(tmp_path, FakeRegistry()).latest("python").latest == "3.13"


def test_an_image_with_no_matching_variant_has_no_answer(tmp_path):
    assert client(tmp_path, FakeRegistry()).latest("python:musl") is None


def test_an_image_the_registry_does_not_have_is_none(tmp_path):
    assert client(tmp_path, FakeRegistry()).latest("nosuchimage") is None


def test_a_repository_with_no_tags_at_all_is_not_the_same_as_no_repository(tmp_path):
    net = FakeRegistry(tags={"library/empty": None})
    assert client(tmp_path, net).latest("empty") is None


# ---------- names ----------
@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("python", (DOCKER_HUB, "library/python")),
        ("owner/image", (DOCKER_HUB, "owner/image")),
        ("ghcr.io/owner/name", ("ghcr.io", "owner/name")),
        ("mcr.microsoft.com/playwright/python", ("mcr.microsoft.com", "playwright/python")),
        ("localhost:5000/thing", ("localhost:5000", "thing")),
        ("quay.io/org/app", ("quay.io", "org/app")),
    ],
)
def test_where_an_image_lives(reference, expected):
    """A first segment with a dot or a port is a host; everything else is Docker Hub, which is why `ghcr.io/owner/name` and `owner/name`
    mean different places."""
    assert split_reference(reference) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("python:slim", ("python", "slim")),
        ("python", ("python", "")),
        ("ghcr.io/owner/tool", ("ghcr.io/owner/tool", "")),
        ("mcr.microsoft.com/playwright/python:jammy", ("mcr.microsoft.com/playwright/python", "jammy")),
        ("localhost:5000/thing", ("localhost:5000/thing", "")),
    ],
)
def test_the_variant_is_read_off_the_name_the_way_a_tag_is(name, expected):
    assert split_variant(name) == expected


def test_an_official_image_is_asked_about_under_library(tmp_path):
    net = FakeRegistry()
    client(tmp_path, net).latest("python")
    assert any("/v2/library/python/tags/list" in url for url, _ in net.calls)
