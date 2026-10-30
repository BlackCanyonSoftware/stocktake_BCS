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
from stocktake.check import run_check
from stocktake.config import CONFIG_NAME, ConfigError
from stocktake.init_project import FAILED, WRITTEN, init_project
from stocktake.models import Report
from stocktake.readers import InstalledFn
from stocktake.registries import Registries
from stocktake.report import FORMATS, ONLY_CHOICES, render_json, render_sarif, render_summary, render_text
from stocktake.vendor import VENDORED_NAME, VendorError, write

OK = 0
UNSAFE = 1
INCOMPLETE = 2

EPILOG = """other commands:
  stocktake init        write the check into this project's test suite (`stocktake init --help`)
  stocktake vendor      write the core as one self-contained file (`stocktake vendor --help`)

exit codes:
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
    parser.add_argument(
        "--format",
        choices=list(FORMATS),
        default="text",
        help="text to read, json for another program, sarif for an editor or GitHub code scanning, summary for one line",
    )
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


def _rendered(report: Report, args: argparse.Namespace) -> str:
    if args.format == "json":
        return render_json(report)
    if args.format == "sarif":
        return render_sarif(report, args.only)
    if args.format == "summary":
        return render_summary(report)
    return render_text(report, args.only, args.all_advisories)


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
        report = run_check(
            project,
            config_path=Path(args.config).expanduser() if args.config else None,
            environment=args.environment,
            registries=registries,
            installed=installed,
            today=today,
            refresh=args.refresh,
        )
    except ConfigError as exc:
        print(f"stocktake: {exc}", file=sys.stderr)
        return INCOMPLETE

    out(_rendered(report, args))

    if report.offline:
        return INCOMPLETE
    return UNSAFE if report.failed else OK


def init(argv: Sequence[str] | None = None, *, root: Path | None = None, out: Callable[[str], object] = print) -> int:
    """`stocktake init`: write the dependency check into a project's test suite."""
    parser = argparse.ArgumentParser(
        prog="stocktake init",
        description="Write the dependency check into this project's test suite, and a starter config file.",
        epilog="Nothing is overwritten unless you pass --force. Afterwards, `pytest` runs the check with the rest of your suite.",
    )
    parser.add_argument("path", nargs="?", metavar="PATH", help="the project to write into (default: the current directory)")
    parser.add_argument("--tests", metavar="PATH", help="where to put the test file (default: this project's tests/ directory)")
    parser.add_argument("--force", action="store_true", help="overwrite a file that already exists")
    args = parser.parse_args(argv)

    project = Path(args.path).expanduser().resolve() if args.path else (root if root is not None else Path.cwd())
    if not project.is_dir():
        print(f"stocktake: {project} is not a directory", file=sys.stderr)
        return INCOMPLETE

    tests = Path(args.tests).expanduser() if args.tests else None
    if tests is not None and not tests.is_absolute():
        tests = project / tests

    results = init_project(project, tests, args.force)
    for written in results:
        shown = written.path.relative_to(project).as_posix() if written.path.is_relative_to(project) else str(written.path)
        if written.outcome == WRITTEN:
            out(f"wrote {shown}")
        else:
            out(f"{shown}: {written.detail}")

    if any(w.outcome == FAILED for w in results):
        return INCOMPLETE
    if any(w.outcome == WRITTEN for w in results):
        out("")
        out("Run `pytest` and the dependency check runs with the rest of your suite.")
    return OK


def vendor(argv: Sequence[str] | None = None, *, root: Path | None = None, out: Callable[[str], object] = print) -> int:
    """`stocktake vendor`: write the core as one self-contained file, for a project that cannot take a dependency."""
    parser = argparse.ArgumentParser(
        prog="stocktake vendor",
        description="Write StockTake's core as one self-contained Python file, with no dependencies and nothing to install.",
        epilog=(
            "The file is generated from this package, so it is always overwritten: refreshing the copy is the point of the command, and the "
            "file itself says not to edit it. It is a library, not a command: import it and call run_check(). The pytest plugin, "
            "`stocktake init` and the command line are not in it."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        metavar="PATH",
        help=f"a directory to write {VENDORED_NAME} into, or the file to write (default: the current directory)",
    )
    args = parser.parse_args(argv)

    target = Path(args.path).expanduser() if args.path else (root if root is not None else Path.cwd())
    try:
        written = write(target)
    except VendorError as exc:
        print(f"stocktake: the copy could not be generated: {exc}", file=sys.stderr)
        return INCOMPLETE
    except OSError as exc:
        print(f"stocktake: {target} could not be written ({exc})", file=sys.stderr)
        return INCOMPLETE

    out(f"wrote {written}")
    out("")
    out("Import it and call run_check(); the docstring at the top of the file shows how.")
    return OK


SUBCOMMANDS = ("init", "vendor")


def main(argv: Sequence[str] | None = None) -> int:
    """The console script entry point."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "init":
        return init(arguments[1:])
    if arguments and arguments[0] == "vendor":
        return vendor(arguments[1:])
    return run(arguments)
