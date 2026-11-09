"""`pnpm-lock.yaml`: every package pnpm resolved, read through the YAML subset.

One lock file is worth a great many manifests. The one real pnpm project here is 5719 lines and 653 packages, every one of them invisible
until now — which is why this was worth doing on the strength of a single file.

Two things decide which part of the file to read. `packages:` keys are the plain thing, `name@version`; `snapshots:` keys carry
peer-dependency suffixes in parentheses — `@babel/core@7.29.7(supports-color@8.1.1)`, and nested ones besides — and name the same packages
again. So `packages:` is read and `snapshots:` is ignored, and nothing has to unpick a parenthesis.

The name and the version are separated by the **last** `@`, because a scoped package begins with one: `@babel/code-frame@7.29.7` is
`@babel/code-frame` at `7.29.7`.

**A key that is neither a package nor a recognised non-package is refused**, not skipped. pnpm's layout has changed between major lock
versions before and will again; a reader that quietly found nothing in a file whose shape had moved under it is the failure
[ADR 0009](adr/0009-an-unread-file-makes-the-run-incomplete.md) and [ADR 0013](adr/0013-a-strict-yaml-subset-rather-than-a-dependency.md)
exist to prevent. What that buys: a lock this understands is read, a future one that keeps the shape is read too, and one that does not says
so instead of reporting an empty project.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from stocktake.models import Dep
from stocktake.readers.base import Context, UnreadableManifest, reader
from stocktake.readers.yamlish import parse

FILE_NAME = "pnpm-lock.yaml"

# `name@1.2.3` or `@scope/name@1.2.3`, with an optional leading `/` as older lock versions wrote it. The version is whatever follows the
# last `@`; it is not validated as semver here, because a lock file records what was installed and that is the answer either way.
PACKAGE_KEY = re.compile(r"^/?(?P<name>@[^/@]+/[^/@]+|[^/@][^@]*)@(?P<version>[^@/]+)$")

# Resolved from somewhere no registry knows: a workspace sibling, a tarball, a directory, a git URL. Skipped deliberately, exactly as the
# npm lock reader skips a `resolved` that is not an HTTP URL.
NOT_FROM_A_REGISTRY = ("link:", "file:", "workspace:", "git+", "http:", "https:")


def is_pnpm_lock(path: Path) -> bool:
    return path.name == FILE_NAME


def locked_packages(data: Any, where: str) -> list[tuple[str, str]]:
    """Every `(name, version)` under `packages:`.

    Raises when `packages:` is missing or holds a key this does not recognise, which is the whole safety of reading a format by its shape
    rather than by its version number.
    """
    packages = data.get("packages") if isinstance(data, dict) else None
    if packages is None:
        version = data.get("lockfileVersion") if isinstance(data, dict) else None
        named = f" (lockfileVersion {version})" if version else ""
        raise UnreadableManifest(f"{where}: has no `packages:` section{named}, so its layout is not one StockTake reads")
    if not isinstance(packages, dict):
        raise UnreadableManifest(f"{where}: `packages:` is not a mapping, so its layout is not one StockTake reads")

    found = []
    for key in packages:
        if any(marker in key for marker in NOT_FROM_A_REGISTRY):
            continue  # a workspace sibling or a tarball: real, and nothing a registry can be asked about
        match = PACKAGE_KEY.match(key)
        if match is None:
            raise UnreadableManifest(f"{where}: `packages:` holds {key!r}, which is not a name and a version this reader understands")
        found.append((match.group("name"), match.group("version")))
    return found


@reader("npm", is_pnpm_lock)
def read_pnpm_lock(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Packages resolved by a pnpm-lock.yaml."""
    for name, version in dict.fromkeys(locked_packages(parse(text, path.name), path.name)):
        yield Dep("npm", name, version, context.source(path), f"=={version}", "locked")
