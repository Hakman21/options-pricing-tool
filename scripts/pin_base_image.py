"""Pin the Dockerfile's base image to an exact content hash.

    python scripts/pin_base_image.py           # pin to the current digest
    python scripts/pin_base_image.py --check   # report only, change nothing
    python scripts/pin_base_image.py --unpin   # go back to the plain tag

Why this exists
---------------
`FROM python:3.12-slim` names a *tag*. A tag is a movable label: Docker Hub
repoints it at a new image every time they publish a patch or a security fix. So
building today and building in three months can pull genuinely different operating
systems, and "it worked last month" stops being a statement anyone can verify.

A *digest* is a SHA-256 hash of the image's actual bytes:

    FROM python:3.12-slim@sha256:1a2b3c...

Change one byte anywhere in that image and the hash changes, so a digest can only
ever resolve to the exact same thing. That is what makes a build reproducible.

The tag is kept alongside the digest deliberately - the tag tells a human what the
image is, the digest is what Docker actually enforces.

The trade-off
-------------
A pinned image stops receiving security patches until someone updates the pin. That
is the point: updates become a deliberate, reviewable change instead of something
that silently happens between two builds. `.github/dependabot.yml` opens a pull
request when a newer digest appears, so the pin stays fresh without being automatic.

Requires Docker running locally, because resolving a digest means asking a registry.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from _common import BACKEND, banner, cyan, dim, green, red, yellow

DOCKERFILE = BACKEND / "Dockerfile"

# Matches `FROM python:3.12-slim`, with or without an existing @sha256:... and with
# or without a trailing `AS stage`.
FROM_LINE = re.compile(
    # [ \t]* rather than \s* for the trailing run: \s matches newlines, which would
    # swallow the blank line after each FROM and silently reformat the file.
    r"^(?P<prefix>FROM[ \t]+)(?P<image>[^\s@]+)(?P<digest>@sha256:[0-9a-f]{64})?"
    r"(?P<suffix>[ \t]+AS[ \t]+\S+)?[ \t]*$",
    re.MULTILINE,
)


def resolve_digest(image: str) -> str | None:
    """Ask the local Docker daemon for the image's content hash."""
    print(f"  pulling {image} ...", end="", flush=True)
    pull = subprocess.run(
        ["docker", "pull", image], capture_output=True, text=True, check=False
    )
    if pull.returncode != 0:
        print(red(" failed"))
        print(dim((pull.stderr or pull.stdout).strip()[:400]))
        return None
    print(green(" done"))

    inspect = subprocess.run(
        ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspect.returncode != 0 or "@sha256:" not in inspect.stdout:
        print(red("  could not read a digest for that image"))
        return None

    # docker prints `python@sha256:...`; we only want the hash part.
    return "@sha256:" + inspect.stdout.strip().split("@sha256:")[1]


def main() -> int:
    check_only = "--check" in sys.argv
    unpin = "--unpin" in sys.argv

    banner("Base image pinning")

    if not DOCKERFILE.exists():
        print(red(f"No Dockerfile at {DOCKERFILE}"))
        return 1

    text = DOCKERFILE.read_text()
    matches = list(FROM_LINE.finditer(text))
    if not matches:
        print(red("No FROM lines found - has the Dockerfile changed shape?"))
        return 1

    images = {m.group("image") for m in matches}
    pinned = {m.group("image") for m in matches if m.group("digest")}

    print(f"  {len(matches)} FROM lines, {len(images)} distinct image(s)")
    for image in sorted(images):
        state = green("pinned") if image in pinned else yellow("tag only")
        print(f"    {image:<28} {state}")

    if check_only:
        print()
        if pinned == images:
            print(green("Every base image is pinned to a digest."))
            return 0
        print(yellow("Not every base image is pinned. Run without --check to fix."))
        return 1

    if unpin:
        updated = FROM_LINE.sub(
            lambda m: f"{m.group('prefix')}{m.group('image')}{m.group('suffix') or ''}", text
        )
        DOCKERFILE.write_text(updated)
        print()
        print(green("Digests removed; the Dockerfile now uses plain tags."))
        return 0

    # Resolve each distinct image once, then rewrite every line that uses it.
    print()
    digests: dict[str, str] = {}
    for image in sorted(images):
        digest = resolve_digest(image)
        if digest is None:
            print()
            print(red("Could not resolve a digest. Is Docker running?"))
            return 1
        digests[image] = digest
        print(f"    {image} -> {dim(digest)}")

    def replace(match: re.Match[str]) -> str:
        image = match.group("image")
        return (
            f"{match.group('prefix')}{image}{digests[image]}{match.group('suffix') or ''}"
        )

    updated = FROM_LINE.sub(replace, text)

    if updated == text:
        print()
        print(green("Already pinned to these digests; nothing to change."))
        return 0

    DOCKERFILE.write_text(updated)
    print()
    print(green(f"Pinned {len(matches)} FROM line(s) in {DOCKERFILE.name}."))
    print()
    print("  Verify with:")
    print(f"    {cyan('docker build -t options-pricing-api:local backend')}")
    print()
    print(dim("  Commit the change. Dependabot will raise a PR when a newer digest"))
    print(dim("  appears, so the pin stays current without updating silently."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
