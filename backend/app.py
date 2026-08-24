"""ASGI entrypoint for platforms that load an app by file rather than by module.

The application itself lives in `src/api/main.py`. This file exists because
Vercel's Python runtime resolves an entrypoint to a *path relative to the project
root* - `app.py`, `index.py`, `main.py`, or the same names one level down in
`src/` or `app/`. A src-layout package like `api.main` is a module path, not a
file path, so it is never found by that search. Two lines here are cheaper than
restructuring the package to suit one deployment target.

The `sys.path` insertion covers the case where the project has not been installed
into the environment. Vercel does install it, and so does the container, in which
case `api` already imports and the insertion changes nothing - but a bare
`uvicorn app:app` from this directory then works too, which makes the file
testable rather than something you can only find out about by deploying.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from api.main import app  # noqa: E402  (import must follow the path setup above)

__all__ = ["app"]
