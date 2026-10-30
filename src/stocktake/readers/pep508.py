"""What a Python requirement looks like, in one place.

Both the Dockerfile reader and the manifest readers need to turn `pillow==12.3.0`, `requests>=2.30`, `uvicorn[standard]>=0.30` and a bare
`ruff` into the same three facts, so that knowledge lives here rather than in two regular expressions that drift apart.
"""

from __future__ import annotations

import re

BARE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
REQUIREMENT = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*)(\[[^\]]*\])?\s*(===|==|~=|>=|<=|!=|>|<)\s*([^\s,;]+)(.*)$")


def parse_requirement(entry: str) -> tuple[str, str | None, str] | None:
    """One requirement as (name, pinned version or None, specifier as written), or None when it is not a package requirement at all.

    Only `==` and `===` count as a pinned version. Everything else — a range, a compatible release, nothing at all — leaves the version open,
    which is a finding in itself rather than something to pass over.
    """
    text = entry.split(";", 1)[0].strip()  # an environment marker says when it applies, not what it is
    if not text:
        return None
    match = REQUIREMENT.match(text)
    if match:
        name, _extras, operator, version, rest = match.groups()
        pinned = version if operator in ("==", "===") else None
        return name, pinned, f"{operator}{version}{rest}".strip()
    name = re.split(r"[\s<>=!~\[(]", text, maxsplit=1)[0]
    return (name, None, "") if BARE_NAME.match(name) else None
