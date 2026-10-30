"""Rendering a report. Pure functions of a `Report`: nothing here re-reads a file or asks a registry anything (docs/ARCHITECTURE.md)."""

from stocktake.report.json import as_dict, render_json
from stocktake.report.text import ONLY_CHOICES, render_text

__all__ = ["ONLY_CHOICES", "as_dict", "render_json", "render_text"]
