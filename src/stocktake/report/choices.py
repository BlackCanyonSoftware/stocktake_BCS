"""Which statuses a narrowed report shows.

Shared by every format, so `--only vulnerable` means the same thing whether the answer comes back as text, as JSON or as SARIF.
"""

from __future__ import annotations

from stocktake.models import STATUSES

ONLY_CHOICES: tuple[str, ...] = ("all", "outdated", "vulnerable")

# `accepted` is in every set, including the narrowest. `--only vulnerable` asks "what is unsafe here", and a package carrying forty-six
# advisories is unsafe whether or not somebody signed for it. Narrowing is for hiding what needs no action, not for hiding risk.
_SHOWN_FOR: dict[str, frozenset[str]] = {
    "all": frozenset(STATUSES),
    "outdated": frozenset({"vulnerable", "yanked", "accepted", "outdated"}),
    "vulnerable": frozenset({"vulnerable", "yanked", "accepted"}),
}


def shown_statuses(only: str = "all") -> frozenset[str]:
    """The statuses a report narrowed to `only` should include. An unrecognised value shows everything rather than nothing."""
    return _SHOWN_FOR.get(only, _SHOWN_FOR["all"])
