"""StockTake: a stock-take of what your project depends on.

Reads what the project pins, asks the public registries whether a newer release exists and whether the pinned one has a known advisory, and
fails only when something is actually unsafe. It never edits a file, never needs an account, and sends nothing but package names and versions.

The short version, in code:

    from pathlib import Path
    from stocktake import run_check, render_text

    report = run_check(Path("."))
    print(render_text(report))
    assert not report.failed and report.complete

See docs/ARCHITECTURE.md for the shape and docs/adr/ for why it is that shape.
"""

from stocktake._version import __version__
from stocktake.check import failure_text, incomplete_text, run_check, skip_reason, update_warning
from stocktake.config import Config, ConfigError, load_config
from stocktake.evaluate import evaluate
from stocktake.models import Advisory, Dep, DependencyUpdateAvailable, Finding, Report, Unread, Unreadable
from stocktake.policy import Policy, PolicyEntry
from stocktake.registries import Cache, OfflineError, RateLimited, Registries
from stocktake.report import render_json, render_text
from stocktake.scan import scan, unread_manifests

__all__ = [
    "Advisory",
    "Cache",
    "Config",
    "ConfigError",
    "Dep",
    "DependencyUpdateAvailable",
    "Finding",
    "OfflineError",
    "Policy",
    "PolicyEntry",
    "RateLimited",
    "Registries",
    "Report",
    "Unread",
    "Unreadable",
    "__version__",
    "evaluate",
    "failure_text",
    "incomplete_text",
    "load_config",
    "render_json",
    "render_text",
    "run_check",
    "scan",
    "skip_reason",
    "unread_manifests",
    "update_warning",
]
