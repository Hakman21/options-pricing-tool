#!/usr/bin/env bash
# Thin wrapper; the logic is in dev.py so it is identical on every platform.
exec python3 "$(dirname "${BASH_SOURCE[0]}")/dev.py" "$@"
