"""Rendering a report. Pure functions of a `Report`: nothing here re-reads a file or asks a registry anything (docs/ARCHITECTURE.md)."""

from stocktake.report.choices import ONLY_CHOICES, shown_statuses
from stocktake.report.json import as_dict, render_json
from stocktake.report.sarif import as_sarif, render_sarif
from stocktake.report.summary import render_summary
from stocktake.report.text import render_text

# The formats `--format` accepts, and what renders each. Text first: it is the default and the one people read.
FORMATS = ("text", "json", "sarif", "summary")

__all__ = [
    "FORMATS",
    "ONLY_CHOICES",
    "as_dict",
    "as_sarif",
    "render_json",
    "render_sarif",
    "render_summary",
    "render_text",
    "shown_statuses",
]
