# syntax=docker/dockerfile:1.7
#
# Multi-stage build for the pricing API.
#
# The builder stage has a compiler toolchain and uv; the runtime stage has neither.
# That keeps the shipped image smaller and, more importantly, removes an entire
# category of thing an attacker could use if they ever got code execution inside it.
#
# Expect roughly 250 MB. NumPy and SciPy are genuinely large - anyone quoting 50 MB
# for a scientific Python image is not shipping SciPy.

# The Python minor version is deliberate, not incidental. It has to match the CI
# matrix and `requires-python` in pyproject.toml, because the image is the thing
# people actually run - shipping an interpreter the test suite never exercises is
# how a green pipeline stops meaning anything. Dependabot is configured to propose
# patch updates only for this reason (.github/dependabot.yml).
#
# Moving it is a three-part change: this file, the CI matrix, and a check that the
# new base image does not ship its own vulnerable packages. python:3.14-slim, for
# instance, currently bundles a setuptools with a published CVE.

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 - build the virtual environment
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# UV_COMPILE_BYTECODE trades a slower build for a faster cold start, which is the
# right trade for a scale-to-zero deployment where every request may be the first.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir uv==0.12.5

WORKDIR /app

# Dependency manifests are copied *before* the source. Docker invalidates every
# layer after the first one that changes, so editing a Python file re-runs only the
# final sync instead of reinstalling NumPy and SciPy. This ordering is the single
# biggest difference between a pleasant and an infuriating development loop.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Now the source, and a second sync that installs the project itself.
#
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 - runtime
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Apply pending Debian security updates.
#
# Official base images are rebuilt on their own schedule, so they lag the Debian
# security archive - often by a week or more. Upgrading here means the image never
# ships a package that already has a published fix.
#
# This composes with `ignore-unfixed: true` on the Trivy scan in CI: unfixed
# advisories are skipped because nothing can be done about them, and fixed ones are
# applied automatically by this line. The gate therefore only fails when a fix
# exists that the build did not pick up, which is a real problem worth stopping for.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Build metadata, passed in by CI so a running container can report exactly which
# commit produced it (see GET /api/v1/meta).
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    OPT_GIT_SHA=${GIT_SHA} \
    OPT_BUILD_TIME=${BUILD_TIME}

# A fixed high UID rather than a name lookup: it stays stable if the image is run
# under a runtime that maps users differently, and it is never 0.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv
COPY --from=builder --chown=10001:10001 /app/src /app/src

USER 10001
EXPOSE 8000

# Hits the liveness probe, which deliberately touches no dependencies - a health
# check that calls an upstream will kill the container during an upstream outage.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# One worker by default: the container is expected to scale horizontally, and the
# pricing work is CPU-bound NumPy that already releases the GIL. Override with
# WEB_CONCURRENCY on a larger box.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
