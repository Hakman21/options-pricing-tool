"""Run every check: linting, type checking, both test suites, and a build.

    python scripts/check.py            # summary only, full output for failures
    python scripts/check.py --verbose  # full output for everything

Nothing here needs the servers running: the backend tests call the app in-process
and the frontend tests mock the network.

Every failing step prints its complete output, so if something breaks you have
something concrete to read rather than "it didn't work".
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from _common import (
    BACKEND,
    FRONTEND,
    banner,
    cyan,
    dim,
    find_npm,
    green,
    red,
    require_setup,
    run,
    yellow,
)


@dataclass
class Step:
    name: str
    cmd: list[str]
    cwd: object
    why: str


def main() -> int:
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    py = require_setup()
    npm = find_npm()
    if npm is None:
        print(red("npm was not found on your PATH. Install Node.js and reopen your terminal."))
        return 1

    steps = [
        Step("ruff (lint)", [str(py), "-m", "ruff", "check", "src", "tests"], BACKEND,
             "style and common-bug rules"),
        Step("ruff (format)", [str(py), "-m", "ruff", "format", "--check", "src", "tests"], BACKEND,
             "consistent formatting"),
        Step("mypy (types)", [str(py), "-m", "mypy"], BACKEND,
             "strict static type checking"),
        Step("pytest", [str(py), "-m", "pytest", "--cov", "--cov-report=term-missing",
                        "--cov-fail-under=90"], BACKEND,
             "full suite, 90% coverage floor"),
        Step("eslint", [npm, "run", "lint"], FRONTEND, "frontend linting"),
        Step("prettier", [npm, "run", "format:check"], FRONTEND, "frontend formatting"),
        Step("tsc", [npm, "exec", "--", "tsc", "--noEmit"], FRONTEND, "TypeScript type checking"),
        Step("vitest", [npm, "run", "test"], FRONTEND, "21 frontend tests"),
        Step("vite build", [npm, "exec", "--", "vite", "build"], FRONTEND, "production bundle"),
    ]

    banner("Running every check")
    failures: list[tuple[Step, str]] = []

    for step in steps:
        print(f"  {step.name:<16} {dim(step.why)} ... ", end="", flush=True)
        result = run(step.cmd, step.cwd, capture=not verbose)

        if result.returncode == 0:
            print(green("pass"))
            if verbose and result.stdout:
                print(dim(result.stdout))
        else:
            print(red("FAIL"))
            output = ""
            if not verbose:
                output = (result.stdout or "") + (result.stderr or "")
            failures.append((step, output))

    print()
    if not failures:
        print(green("All checks passed."))
        return 0

    for step, output in failures:
        banner(f"FAILED: {step.name}")
        print(dim(f"$ {' '.join(step.cmd)}"))
        print(output.strip() or "(no output captured - rerun with --verbose)")

    print()
    print(red(f"{len(failures)} of {len(steps)} checks failed: ")
          + ", ".join(s.name for s, _ in failures))
    print(yellow("Copy the output above if you want help diagnosing it."))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
