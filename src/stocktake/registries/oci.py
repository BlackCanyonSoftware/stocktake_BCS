"""Container registries: the newest tag of a base image, from Docker Hub, GitHub's registry, Microsoft's, or any other that speaks OCI.

The first client here that needs a credential to read something entirely public. Docker Hub and `ghcr.io` both answer a plain tag listing
with `401` and a `WWW-Authenticate` header naming a token service that will hand anyone a token for a public image; `mcr.microsoft.com`
answers without one. So the flow is: ask, and if the answer is "not without a token", get one and ask again. That is the registry's own
handshake rather than a special case per host, which is what lets one client cover registries nobody here has tried
([ADR 0012](adr/0012-container-base-images.md)).

**These get no advisory check**, exactly as GitHub release downloads do not: OSV has no ecosystem for a container image, so the report says
only whether a newer tag exists and never claims the image is free of known problems. What is inside the image — its distro packages — is a
different question that this does not answer either.

The other half of the problem is that a container tag is not a version. `python:3.12-slim` names a *variant* as well as a version, and the
newest tag of that image is some `3.14-rc` of a different variant; recommending it would be telling somebody on `-slim` to move to an image
that is not slim. So a variant is carried as part of the name and only tags of the same variant are ever compared.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from stocktake.registries.base import Versions
from stocktake.registries.http import Cache, Unauthorized
from stocktake.versions import container_tag, release_tuple

# Where a bare `python` lives. Docker Hub is the only registry that is implied by a name with no host in it.
DOCKER_HUB = "registry-1.docker.io"
DOCKER_HUB_NAMES = frozenset({"docker.io", "index.docker.io", "registry.hub.docker.com", DOCKER_HUB})

# An image whose repository has no slash is an official one, and officials live under `library/`: `python` is really `library/python`.
OFFICIAL_NAMESPACE = "library"

TAGS_URL = "https://{registry}/v2/{repository}/tags/list"

# The conventional token endpoint. Both registries that need one put it here and name themselves as the service; a registry that does not
# need one never gets asked. A host doing something else entirely answers 401 twice and the image is reported `unknown` with the reason,
# which is the honest outcome for a registry this does not know how to talk to.
TOKEN_URL = "https://{host}/token?service={service}&scope=repository:{repository}:pull"  # noqa: S105  (a URL, not a secret)
TOKEN_HOSTS = {DOCKER_HUB: ("auth.docker.io", "registry.docker.io")}


def split_variant(name: str) -> tuple[str, str]:
    """A client name back into (image reference, variant). The variant is empty when there is none.

    The reader writes `python:slim` for the slim variant of the python image, so that two Dockerfiles using different variants of one image
    are two different things to ask about. The separator is the one Docker itself uses, and it is read the same way a tag is: after the last
    `/`, so a registry's port (`localhost:5000/thing`) is never mistaken for it.
    """
    head, separator, tail = name.rpartition(":")
    return (head, tail) if separator and "/" not in tail else (name, "")


def split_reference(reference: str) -> tuple[str, str]:
    """An image reference into (registry host, repository path).

    The first segment is a host when it looks like one — it has a dot or a port, or it is `localhost`. Everything else is a repository on
    Docker Hub, which is the rule Docker itself uses and the reason `ghcr.io/owner/name` and `owner/name` mean different places.
    """
    head, _, tail = reference.partition("/")
    if tail and ("." in head or ":" in head or head == "localhost"):
        return head, tail
    return DOCKER_HUB, reference if "/" in reference else f"{OFFICIAL_NAMESPACE}/{reference}"


class OCI:
    ecosystem = "Docker"

    def __init__(self, cache: Cache) -> None:
        self.cache = cache

    @staticmethod
    def keep(data: Any) -> dict[str, Any] | None:
        """The newest version of each variant, out of a listing that ran to 4117 tags for one image.

        This is the whole of what is ever read. `latest` is asked about one variant and takes the largest version in it, so a map from
        variant to its newest version loses nothing and turns 89 KB of cache into a few hundred bytes. Tags that name no version -- a
        codename, `latest`, an alpha -- are dropped here for the same reason: they are never an answer.
        """
        if not isinstance(data, dict):
            return None
        tags = data.get("tags")
        # A repository that exists with no tags answers `{"tags": null}`, which is not the same as no such repository: an empty map, not None.
        newest: dict[str, str] = {}
        for tag in tags if isinstance(tags, list) else []:
            parts = container_tag(str(tag))
            if parts is None:
                continue
            version, variant = parts
            if variant not in newest or release_tuple(version) > release_tuple(newest[variant]):
                newest[variant] = version
        return {"newest": newest}

    def _newest(self, registry: str, repository: str) -> dict[str, str] | None:
        """The newest version of every variant this repository publishes, getting a token first only if told to."""
        url = TAGS_URL.format(registry=registry, repository=quote(repository, safe="/"))
        try:
            data = self.cache.get(url, keep=self.keep)
        except Unauthorized:
            token = self._token(registry, repository)
            data = self.cache.get(url, headers={"Authorization": f"Bearer {token}"}, keep=self.keep)
        if not data:
            return None
        return dict(data.get("newest") or {})

    def _token(self, registry: str, repository: str) -> str:
        host, service = TOKEN_HOSTS.get(registry, (registry, registry))
        url = TOKEN_URL.format(host=host, service=service, repository=quote(repository, safe="/"))
        data = self.cache.once(url)  # never cached: it is good for minutes and this cache keeps answers for hours
        token = (data or {}).get("token") or (data or {}).get("access_token")
        if not token:
            raise Unauthorized(f"{registry} would not issue a token for {repository}")
        return str(token)

    def latest(self, name: str) -> Versions | None:
        """The newest tag of this image **of the same variant**, or None when the registry has no such repository.

        Only tags carrying a version are considered, and only those whose variant matches the one asked about, so `python:slim` is answered
        with the newest `N-slim` and never with a plain `N` or an `N-alpine`.
        """
        reference, variant = split_variant(name)
        registry, repository = split_reference(reference)
        newest = self._newest(registry, repository)
        if newest is None:
            return None
        found = newest.get(variant)
        return Versions(latest=found) if found else None
