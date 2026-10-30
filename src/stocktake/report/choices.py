"""Which statuses a narrowed report shows.

Shared by every format, so `--only vulnerable` means the same thing whether the answer comes back as text, as JSON or as SARIF.
"""

from __future__ import annotations

from stocktake.models import STATUSES

ONLY_CHOICES: tuple[str, ...] = ("all", "outdated", "vulnerable")

_SHOWN_FOR: dict[str, frozenset[str]] = {
    "all": frozenset(STATUSES),
    "outdated": frozenset({"vulnerable", "yanked", "outdated"}),
    "vulnerable": frozenset({"vulnerable", "yanked"}),
}


def shown_statuses(only: str = "all") -> frozenset[str]:
    """The statuses a report narrowed to `only` should include. An unrecognised value shows everything rather than nothing."""
    return _SHOWN_FOR.get(only, _SHOWN_FOR["all"])
