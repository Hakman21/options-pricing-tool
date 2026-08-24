# 4. Local-first, with the container as an artefact rather than a requirement

Status: accepted

## Context

This is a local project. There is no hosting target and no deployment. It still
needs a container image, because building one is the only way to know the
application is genuinely portable rather than dependent on one machine's state.

Two ways of arranging that pull in opposite directions:

- **Container-first.** `docker compose up` is the documented way to run everything.
  Honest about the deployment story, but it means a first run requires installing a
  container runtime before anyone can see three numbers.
- **Local-first.** Python and Node run the app directly; the image exists and is
  tested but is not on the critical path.

## Decision

Local-first. The default path requires **Python and Node, and nothing else**.

1. `scripts/setup.py`, `dev.py` and `check.py` are the entry points. They are Python
   rather than shell scripts precisely so the same code runs on Windows, macOS and
   Linux and can be tested once instead of per-platform.
2. Plain `pip` and `venv`, not `uv`. `uv` is faster and `uv.lock` is kept for CI and
   the image, but requiring it would add an install before the first run. The dev
   dependencies are mirrored into `[project.optional-dependencies]` so
   `pip install -e ".[dev,market]"` works with a stock Python.
3. The frontend's `base` is `/` and the app runs at the root. The Vite dev server
   proxies `/api` to the Python process, so both halves are on one origin and there
   is no CORS configuration anywhere.
4. The API's docs live under `/api` (`/api/docs`, `/api/openapi.json`) so a single
   proxy rule covers the entire browser-facing surface. `/health` and `/ready` stay
   at the root: they are for whatever supervises the process, not the browser.
5. The image is built and **booted** by CI on every push, so it cannot rot while
   unused.

## Consequences

- First run is two commands on a machine with Python and Node.
- The container is still real. CI starts it, waits for readiness, and prices an
  option over HTTP before the build is allowed to pass.
- `dev.py` detects an API already listening on port 8000 and reuses it, so running
  the container in one terminal and the web app in another works without
  configuration.
- Serving the frontend from a sub-path later means changing `base` in
  `vite.config.ts` and routing `/api/*` ahead of the catch-all. Everything else is
  built relative to `base`, so nothing else would need to change.
