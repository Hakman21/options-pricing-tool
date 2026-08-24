# The container

The API ships as a Docker image. It is not needed for development - `python
scripts/dev.py` is faster to iterate with - but CI builds it and boots it on every
push, so it stays real rather than decorative.

```bash
docker build -t options-pricing-api:local backend
docker run --rm -p 8000:8000 options-pricing-api:local
curl http://localhost:8000/ready
```

The image serves the API only. For the full app, leave the container running and
start the web app alongside it:

```bash
python scripts/dev.py
```

`dev.py` checks port 8000 first. Finding the container already there, it starts only
the web app and points it at the running API. It also reads `/ready` and warns if
that API reports a capability as unavailable.

`docker compose up` runs both halves in containers instead.

---

## What each decision in the Dockerfile is for

**Two stages.** The first installs a compiler toolchain and `uv` to build the virtual
environment; the second copies only the finished environment across. The shipped
image contains no build tools, which makes it smaller and removes an entire category
of thing an attacker could use if they ever got execution inside it.

**Dependencies copied before the source.** Docker caches layers in order and discards
every layer after the first one that changed. Copying `pyproject.toml` and `uv.lock`
first means editing a Python file rebuilds in seconds rather than reinstalling NumPy
and SciPy. This single ordering decision is most of the difference between a pleasant
and an infuriating build loop.

**The `market` extra is installed.** `yfinance` is an optional extra so the pricing
library can be installed without a web scraper attached - useless to anyone importing
`option_pricing` into a notebook. But any deployment serving the UI needs it, because
the UI offers ticker lookup, and an image without it ships a broken button. Live
lookups are switched off with `OPT_MARKET_DATA_ENABLED=false`, which is a
configuration choice rather than a missing dependency.

**A non-root user.** `USER 10001`, a fixed high UID rather than a name lookup. By
default a container runs as root; if the app is ever compromised, that is the
difference between a bad day and a catastrophe.

**A healthcheck that touches nothing.** It calls `/health`, which deliberately has no
dependencies. A healthcheck that called the market data upstream would kill the
container during an upstream outage - precisely when restarting it helps least.
`/ready` is the probe that does check dependencies, and it reports them individually.

**Pending security updates are applied at build time.** Official base images are
rebuilt on their own schedule and lag the Debian security archive, often by a week
or more, so a freshly pulled `python:3.12-slim` routinely contains packages that
already have published fixes. `apt-get upgrade` in the runtime stage closes that gap.

**Build metadata.** `GIT_SHA` and `BUILD_TIME` are passed in by CI and surfaced at
`GET /api/v1/meta`, so a running container can say exactly which commit produced it.

Expect roughly 250 MB. NumPy and SciPy are genuinely large.

---

## The vulnerability gate

CI scans the built image with Trivy and fails on HIGH or CRITICAL findings. Two
settings make that gate stable rather than a source of random red builds:

- **`ignore-unfixed: true`** skips advisories with no available fix. Failing a build
  over something nobody can act on teaches people to ignore the build.
- **`apt-get upgrade` in the Dockerfile** applies every fix that *is* available.

Together they mean the scan only fails when a fix exists and the image did not pick
it up - which is a real problem worth stopping for, and usually means rebuilding.

If a finding is genuinely not exploitable here, record it rather than weakening the
gate. Create `backend/.trivyignore`:

```
# CVE-2026-XXXXX: util-linux mount(8) TOCTOU.
# Not reachable: this container never mounts anything and runs as a non-root user
# with no SUID binaries in its path. Revisit when the base image ships the fix.
CVE-2026-XXXXX
```

Every entry needs a reason and a date to revisit. An ignore file without
justifications is just a disabled scanner.

---

## Tags versus digests

`FROM python:3.12-slim` names a **tag**, and a tag is a movable label. Docker Hub
repoints it every time they publish a patch or a security fix, so building today and
building in three months can pull genuinely different operating systems. Nothing
warns you, and "it worked last month" stops being a claim anyone can check.

A **digest** is a SHA-256 hash of the image's actual bytes:

```dockerfile
FROM python:3.12-slim@sha256:1a2b3c... AS builder
```

Change one byte anywhere in that image and the hash changes, so a digest can only
resolve to exactly the same thing. That is what makes a build reproducible. Keeping
the tag alongside the digest is deliberate: the tag tells a human what the image is,
the digest is what Docker enforces.

The trade-off is that a pinned image stops receiving security patches until someone
updates the pin. That is the point rather than a flaw - updates become a deliberate,
reviewable change instead of something that happens silently between two builds. It
only works if something watches for newer digests, which is what
[`.github/dependabot.yml`](../.github/dependabot.yml) does: weekly, as a pull request.

### Pinning

Resolving a digest means asking a registry, so this needs Docker running:

```bash
python scripts/pin_base_image.py           # resolve and pin
python scripts/pin_base_image.py --check   # report only
python scripts/pin_base_image.py --unpin   # back to plain tags
```

It rewrites every `FROM` line, keeps the tag for readability, and is reversible.
Rebuild afterwards to confirm nothing broke, then commit the change.

---

## Deploying it

Not currently deployed anywhere - this runs locally. The image is host-agnostic if
that changes: it listens on port 8000, runs as a non-root user, and needs no
environment variables to start. Anywhere that runs a container image will take it.

Serving the frontend from a sub-path rather than the root means setting `base` in
`frontend/vite.config.ts` to that path. Everything else - every asset URL, every API
call - is built relative to `base`, so nothing else needs touching. Routing `/api/*`
to the container and everything else to the static build keeps both on one origin and
avoids CORS entirely. See
[ADR 0004](adr/0004-local-first-with-optional-container.md).
