"""One-time setup: create the virtualenv, install both halves.

    python scripts/setup.py

Needs Python 3.12+ and Node.js 20+. Nothing else - no Docker, no make, no uv.

Uses only the standard library, because it has to run before any dependency exists.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from _common import (
    BACKEND,
    FRONTEND,
    IS_WINDOWS,
    banner,
    cyan,
    dim,
    find_node,
    find_npm,
    green,
    red,
    run,
    venv_python,
    yellow,
)

MIN_PYTHON = (3, 12)


def check_prerequisites() -> bool:
    """Verify the toolchain up front, with actionable messages.

    Failing here with a clear explanation beats failing five steps into an install
    with something like 'npm is not recognized'.
    """
    ok = True

    if sys.version_info < MIN_PYTHON:
        print(red(f"  [X] Python {'.'.join(map(str, sys.version_info[:3]))} is too old."))
        print(yellow(f"      {'.'.join(map(str, MIN_PYTHON))} or newer is required."))
        print(yellow("      The pricing code itself runs on 3.11, but the type checker"))
        print(yellow("      does not: NumPy's current stubs use syntax only 3.12+ parses."))
        print(yellow("      Install from https://www.python.org/downloads/, then delete"))
        print(yellow("      backend/.venv and run this script again."))
        ok = False
    else:
        print(green(f"  [ok] Python {'.'.join(map(str, sys.version_info[:3]))}"))

    node = find_node()
    if node is None:
        print(red("  [X] Node.js was not found on your PATH."))
        print(yellow("      Install the LTS build from https://nodejs.org/ "
                     "then open a NEW terminal."))
        ok = False
    else:
        version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        print(green(f"  [ok] Node {version}"))

    npm = find_npm()
    if npm is None:
        print(red("  [X] npm was not found on your PATH."))
        print(yellow("      npm ships with Node.js. If you just installed Node, "
                     "open a NEW terminal."))
        ok = False
    else:
        version = subprocess.run([npm, "--version"], capture_output=True, text=True).stdout.strip()
        print(green(f"  [ok] npm {version}"))

    return ok


def setup_backend() -> bool:
    venv_dir = BACKEND / ".venv"

    if not venv_dir.exists():
        print("  creating virtual environment ...", end="", flush=True)
        result = run([sys.executable, "-m", "venv", str(venv_dir)], BACKEND, capture=True)
        if result.returncode != 0:
            print(red(" failed"))
            print(result.stderr)
            return False
        print(green(" done"))
    else:
        print(dim("  virtual environment already exists"))

    py = venv_python()
    if not py.exists():
        print(red(f"  [X] Expected an interpreter at {py} but it is not there."))
        return False

    print("  upgrading pip ...", end="", flush=True)
    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "--quiet"], BACKEND, capture=True)
    print(green(" done"))

    # Editable install: `import option_pricing` then works from anywhere without
    # PYTHONPATH, and source edits take effect without reinstalling.
    print("  installing dependencies (a minute or two the first time) ...", end="", flush=True)
    result = run([str(py), "-m", "pip", "install", "-e", ".[dev,market]", "--quiet"],
                 BACKEND, capture=True)
    if result.returncode != 0:
        print(red(" failed"))
        print((result.stdout or "") + (result.stderr or ""))
        return False
    print(green(" done"))
    return True


def setup_frontend() -> bool:
    npm = find_npm()
    assert npm is not None

    lockfile = FRONTEND / "package-lock.json"
    if lockfile.exists():
        # `npm ci` installs exactly what the lockfile pins. `npm install` is free to
        # resolve newer versions within the semver ranges and rewrite the lockfile,
        # which is how two machines end up with different dependency trees and one
        # of them fails lint for reasons the other cannot reproduce.
        cmd, label = [npm, "ci", "--no-fund", "--no-audit"], "npm ci (exact lockfile versions)"
    else:
        cmd, label = [npm, "install", "--no-fund", "--no-audit"], "npm install"

    print(f"  {label} ...", end="", flush=True)
    result = run(cmd, FRONTEND, capture=True)
    if result.returncode != 0:
        print(red(" failed"))
        print((result.stdout or "") + (result.stderr or ""))
        return False
    print(green(" done"))
    return True


def main() -> int:
    banner("Options Pricing Tool - setup")

    print("Checking prerequisites")
    if not check_prerequisites():
        print()
        print(yellow("Install what is missing, open a NEW terminal, and run this again."))
        return 1

    print()
    print("Backend")
    if not setup_backend():
        return 1

    print()
    print("Frontend")
    if not setup_frontend():
        return 1

    print()
    print(green("Setup complete."))
    print()
    print(f"  Start the app:   {cyan('python scripts/dev.py')}")
    print(f"  Run the checks:  {cyan('python scripts/check.py')}")
    print()
    if IS_WINDOWS:
        print(dim("  (or double-click scripts\\dev.cmd and scripts\\check.cmd)"))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
