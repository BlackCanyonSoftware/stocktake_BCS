"""StockTake: a stock-take of what your project depends on.

Reads what the project pins, asks the public registries whether a newer release exists and whether the pinned one has a known advisory, and
fails only when something is actually unsafe. It never edits a file, never needs an account, and sends nothing but package names and versions.

The short version, in code:

    from pathlib import Path
    from stocktake import Registries, evaluate, load_config, render_text, scan

    root = Path(".")
    config = load_config(root)
    report = evaluate(scan(root, config), Registries(), config.policy)
    print(render_text(report))
    assert not report.failed

See docs/ARCHITECTURE.md for the shape and docs/adr/ for why it is that shape.
"""

from stocktake._version import __version__
from stocktake.config import Config, ConfigError, load_config
from stocktake.evaluate import evaluate
from stocktake.models import Advisory, Dep, DependencyUpdateAvailable, Finding, Report, Unread
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
    "__version__",
    "evaluate",
    "load_config",
    "render_json",
    "render_text",
    "scan",
    "unread_manifests",
]
