"""Shared helpers for the setup / dev / check scripts.

These scripts are written in Python rather than PowerShell for one reason: Python
runs identically on Windows, macOS and Linux, so the same code can be tested once
and trusted everywhere. A shell script that only ever runs on one operating system
is a shell script nobody has tested.

Only the standard library is used, because setup.py has to run *before* any
dependencies exist.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

IS_WINDOWS = os.name == "nt"

# Colour, but only where it will actually render. Windows terminals that predate
# Windows 10 do not understand ANSI escapes, and a redirected stream never should.
_COLOUR = sys.stdout.isatty() and (not IS_WINDOWS or os.environ.get("WT_SESSION") or os.environ.get("TERM"))


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOUR else text


def green(t: str) -> str:
    return _c("32", t)


def red(t: str) -> str:
    return _c("31", t)


def yellow(t: str) -> str:
    return _c("33", t)


def cyan(t: str) -> str:
    return _c("36", t)


def dim(t: str) -> str:
    return _c("90", t)


def venv_python() -> Path:
    """Path to the project virtualenv's interpreter, per platform layout."""
    if IS_WINDOWS:
        return BACKEND / ".venv" / "Scripts" / "python.exe"
    return BACKEND / ".venv" / "bin" / "python"


def find_npm() -> str | None:
    """Locate npm.

    On Windows npm is a ``.cmd`` shim, which ``subprocess`` will not find unless it
    is named exactly or resolved first - the single most common cause of
    "npm is not recognized" when calling it from a script.
    """
    return shutil.which("npm.cmd") if IS_WINDOWS else shutil.which("npm")


def find_node() -> str | None:
    return shutil.which("node")


def run(
    cmd: list[str],
    cwd: Path,
    *,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command, returning the completed process rather than raising."""
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=capture,
        # Windows consoles default to a legacy codepage; force UTF-8 so tool output
        # containing characters like ± or σ cannot crash the pipe.
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def require_setup() -> Path:
    """Exit with a helpful message if the virtualenv is missing."""
    py = venv_python()
    if not py.exists():
        print(red("The project is not set up yet."))
        print(f"Run:  {cyan('python scripts/setup.py')}")
        sys.exit(1)
    if not (FRONTEND / "node_modules").exists():
        print(red("Frontend packages are not installed yet."))
        print(f"Run:  {cyan('python scripts/setup.py')}")
        sys.exit(1)
    return py


def banner(title: str) -> None:
    print()
    print(cyan(title))
    print(cyan("=" * len(title)))
