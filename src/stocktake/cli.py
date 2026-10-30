"""The command line: argument parsing, the three exit codes, and nothing else.

The only module that prints or decides an exit code (docs/ARCHITECTURE.md). `run()` takes its collaborators as arguments, so the whole command
can be exercised in a test with a fake network, a temporary project and a fixed date.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

from stocktake._version import __version__
from stocktake.config import CONFIG_NAME, ConfigError, load_config
from stocktake.evaluate import evaluate
from stocktake.readers import InstalledFn
from stocktake.registries import Cache, Registries
from stocktake.report import ONLY_CHOICES, render_json, render_text
from stocktake.scan import NO_ENVIRONMENT_NOTE, find_environment, scan, unread_manifests

OK = 0
UNSAFE = 1
INCOMPLETE = 2

EPILOG = """exit codes:
  0  nothing unsafe. Being behind on a release does not change this.
  1  a vulnerable or withdrawn release, or a policy entry past its date.
  2  the check could not be completed: the registries could not be reached, or the configuration could not be read.

Only package names and versions leave this machine, to pypi.org, api.github.com and api.osv.dev.
No file in the project is ever modified. Answers are cached for six hours; --refresh ignores the cache.
Set GITHUB_TOKEN to raise GitHub's anonymous limit of 60 requests an hour; it is sent to GitHub alone.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stocktake",
        description="Report newer releases and known security advisories for what this project pins.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", metavar="PATH", help="the project to check (default: the current directory)")
    parser.add_argument(
        "--config",
        metavar="PATH",
        help=f"the config file to use (default: {CONFIG_NAME} in the project, else a [tool.stocktake] table in its pyproject.toml)",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text", help="text to read, json for another program")
    parser.add_argument(
        "--only",
        choices=list(ONLY_CHOICES),
        default="all",
        help="narrow the report: everything, what is old or worse, or only what is unsafe",
    )
    parser.add_argument(
        "--environment",
        metavar="PATH",
        help="the Python environment whose installed versions to use, for dependencies declared as a range "
        "(default: the project's own .venv, else the environment active in this shell)",
    )
    parser.add_argument("--refresh", action="store_true", help="ask the registries again instead of using answers cached for six hours")
    parser.add_argument("--all-advisories", action="store_true", help="list every advisory rather than the worst five of each package")
    parser.add_argument("--version", action="version", version=f"stocktake {__version__}")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    registries: Registries | None = None,
    root: Path | None = None,
    out: Callable[[str], object] = print,
    installed: InstalledFn | None = None,
    today: date | None = None,
) -> int:
    """One run of the check. Returns the exit code; prints through `out` so a test can capture it."""
    args = build_parser().parse_args(argv)

    project = Path(args.root).expanduser().resolve() if args.root else (root if root is not None else Path.cwd())
    if not project.is_dir():
        print(f"stocktake: {project} is not a directory", file=sys.stderr)
        return INCOMPLETE

    try:
        config = load_config(project, Path(args.config).expanduser() if args.config else None)
    except ConfigError as exc:
        print(f"stocktake: {exc}", file=sys.stderr)
        return INCOMPLETE

    named = args.environment or config.environment
    chosen = None
    if named is not None:
        chosen = Path(named).expanduser()
        if not chosen.is_absolute():
            chosen = project / chosen  # a path in a config file means a path in that project

    lookup = installed
    notes: list[str] = []
    if lookup is None:
        environment = find_environment(project, chosen)
        if chosen is not None and not environment.found:
            print(f"stocktake: no Python environment found at {chosen}", file=sys.stderr)
            return INCOMPLETE
        lookup = environment.version
        if not environment.found:
            notes.append(NO_ENVIRONMENT_NOTE)

    deps = scan(project, config, lookup)
    # Only worth saying when something actually went unresolved because of it. A Dockerfile's unpinned install is about the image, not us.
    if notes and not any(d.version is None and d.role != "image" for d in deps):
        notes.clear()

    asking = registries if registries is not None else Registries(Cache(ttl=config.cache_ttl_seconds, refresh=args.refresh))
    report = evaluate(deps, asking, config.policy, today, unread_manifests(project, config), notes)
    asking.flush()

    out(render_json(report) if args.format == "json" else render_text(report, args.only, args.all_advisories))

    if report.offline:
        return INCOMPLETE
    return UNSAFE if report.failed else OK


def main(argv: Sequence[str] | None = None) -> int:
    """The console script entry point."""
    return run(argv)
