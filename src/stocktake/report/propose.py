"""The proposals, as a person reads them.

A pure function of what `propose.py` worked out, like every other renderer here: this one opens nothing and decides nothing.

The layout is a diff on purpose. `- old` and `+ new` is the one shape every programmer already reads without being taught, and putting the
two lines under each other makes a wrong proposal obvious at a glance — which matters more here than anywhere else in the report, because
this is the output somebody is about to copy into their own file.
"""

from __future__ import annotations

from collections.abc import Sequence

from stocktake.models import COMMAND, EDIT, Proposal

HEADER = "PROPOSED EDITS. StockTake never applies them: read each one before you do."
NOTHING = "Nothing to propose: nothing here has an upgrade that would change it."


def _heading(proposal: Proposal) -> str:
    dep = proposal.finding.dep
    where = proposal.path + (f":{proposal.line}" if proposal.line else "")
    moving = " (the tag you track, not the newest patch)" if dep.moving else ""
    return f"{where}  {dep.name} {dep.version} -> {proposal.target}{moving}"


def _body(proposal: Proposal) -> list[str]:
    if proposal.kind == EDIT:
        return [f"    - {proposal.before.strip()}", f"    + {proposal.after.strip()}"]
    if proposal.kind == COMMAND:
        return [f"    $ {proposal.command}"]
    return []


def render_propose(proposals: Sequence[Proposal]) -> str:
    """Every proposal, worst first."""
    if not proposals:
        return NOTHING

    lines = [HEADER, ""]
    for proposal in proposals:
        dep = proposal.finding.dep
        if proposal.target:
            lines.append(_heading(proposal))
        else:
            lines.append(f"{proposal.path or dep.source}  {dep.name} {dep.version}")
        lines.append(f"      {proposal.reason}")
        if proposal.note:
            lines.append(f"      {proposal.note}")
        lines += _body(proposal)
        if proposal.link:
            lines.append(f"      {proposal.link}")
        lines.append("")
    return "\n".join(lines).rstrip()
