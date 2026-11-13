"""Run what CI runs, on every Python CI runs it on, before pushing.

CI went red on Python 3.14 and 3.15 after a run on 3.11 alone had passed. Python 3.14 turns an unclosed `HTTPError` into a `ResourceWarning`,
3.11 says nothing, and pytest raises one from garbage collection as a failure of whichever unrelated test is running at the time. Nothing
that was run here could have found it, because the only interpreter used here was the one that does not complain.

So this reads the interpreter list out of `.github/workflows/ci.yml` -- the matrix itself, not a copy that can drift from it -- and runs lint,
formatting, the type check and the tests on each, in an environment of its own.

**A Python that is not installed is reported as missing and fails the run.** It is not skipped quietly. A green result that left an
interpreter out is exactly the false reassurance this project exists to prevent, and a script written to avoid CI surprises should not
produce one. Pass `--allow-missing` to say so on purpose; the missing ones are then named at the end.

    python tools/matrix.py                 # every Python the CI matrix names
    python tools/matrix.py 3.11 3.14       # just these
    python tools/matrix.py --allow-missing # on a machine that has only some of them
    python tools/matrix.py --python 3.14=C:/path/to/python.exe   # a Python the launcher cannot find
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
ENVIRONMENTS = ROOT / ".matrix"

# Run in this order, and stop at the first that fails: a lint error makes the rest of that Python's output noise.
STEPS: tuple[tuple[str, list[str]], ...] = (
    ("lint", ["-m", "ruff", "check", "."]),
    ("format", ["-m", "ruff", "format", "--check", "."]),
    ("types", ["-m", "mypy"]),
    # ResourceWarning as an error because that is what 3.14 does to an unclosed resource, and an older Python can be made to say so too.
    ("tests", ["-m", "pytest", "-q", "-W", "error::ResourceWarning"]),
)


def ci_versions() -> list[str]:
    """The Python versions the CI matrix names, read from the workflow so they cannot drift apart."""
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^\s*python:\s*\[([^\]]+)\]", text, re.MULTILINE)
    if match is None:
        sys.exit(f"could not find the Python matrix in {WORKFLOW}")
    return [item.strip().strip("\"'") for item in match.group(1).split(",")]


def interpreter_for(version: str, explicit: dict[str, str]) -> list[str] | None:
    """The command that starts Python `version`, or None when this machine does not have it."""
    candidates: list[list[str]] = []
    if version in explicit:
        candidates.append([explicit[version]])  # said outright by the person running this, so it is tried first
    if shutil.which("py"):
        candidates.append(["py", f"-{version}"])  # the Windows launcher
    candidates.append([f"python{version}"])
    if shutil.which("uv"):
        candidates.append(["uv", "run", "--python", version, "python"])
    for command in candidates:
        try:
            done = subprocess.run(  # noqa: S603 - fixed candidates, no user input
                [*command, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if done.returncode == 0 and done.stdout.strip() == version:
            return command
    return None


def environment(version: str, interpreter: list[str]) -> Path:
    """A virtual environment for this Python with the project installed in it, made once and then reused."""
    where = ENVIRONMENTS / version
    python = where / ("Scripts" if sys.platform == "win32" else "bin") / ("python.exe" if sys.platform == "win32" else "python")
    if not python.exists():
        subprocess.run([*interpreter, "-m", "venv", str(where)], check=True)  # noqa: S603
        subprocess.run([str(python), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)  # noqa: S603
    # Every run, not only the first: the dev extra moves, and a stale environment is how a local pass and a CI failure come to disagree.
    subprocess.run([str(python), "-m", "pip", "install", "-q", "-e", f"{ROOT}[dev]"], check=True, cwd=ROOT)  # noqa: S603
    return python


def run_on(version: str, interpreter: list[str]) -> str | None:
    """Every step on one Python. The name of the step that failed, or None when all of them passed."""
    python = environment(version, interpreter)
    for name, arguments in STEPS:
        print(f"  [{version}] {name}", flush=True)
        done = subprocess.run([str(python), *arguments], cwd=ROOT, check=False)  # noqa: S603
        if done.returncode != 0:
            return name
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("versions", nargs="*", help="which Pythons to run (default: every one the CI matrix names)")
    parser.add_argument("--python", action="append", default=[], metavar="VERSION=PATH", help="use this interpreter for that version")
    parser.add_argument("--allow-missing", action="store_true", help="do not fail because a Python is not installed here")
    args = parser.parse_args()

    explicit = dict(item.split("=", 1) for item in args.python)
    wanted = args.versions or ci_versions()
    results: dict[str, str] = {}
    for version in wanted:
        print(f"== Python {version}", flush=True)
        interpreter = interpreter_for(version, explicit)
        if interpreter is None:
            results[version] = "MISSING (not installed on this machine)"
            print("  not installed here", flush=True)
            continue
        failed = run_on(version, interpreter)
        results[version] = "ok" if failed is None else f"FAILED at {failed}"

    print("\n== Result")
    for version, outcome in results.items():
        print(f"  Python {version:<5} {outcome}")

    failed = [v for v, o in results.items() if o.startswith("FAILED")]
    missing = [v for v, o in results.items() if o.startswith("MISSING")]
    if failed:
        return 1
    if missing and not args.allow_missing:
        print(
            f"\nNot run: {', '.join(missing)}. CI runs these, so a pass here does not mean CI will pass. Install them, or pass --allow-missing."
        )
        return 2
    if missing:
        print(f"\nNot run, and CI runs them: {', '.join(missing)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
