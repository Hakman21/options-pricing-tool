"""Start the app and stream its logs into one terminal.

    python scripts/dev.py

Runs the Python API on :8000 and the web app on :5173, waits until the API answers,
then opens your browser. Ctrl-C stops both cleanly.

If something is already answering on :8000 - the Docker container, most likely -
that is reused and only the web app starts. So `docker run` in one terminal and this
script in another is a perfectly good way to work.

One terminal rather than two: when something goes wrong, the API error and the
browser request that caused it are interleaved in the order they happened, which is
what you actually want when debugging.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from typing import IO

from _common import (
    BACKEND,
    FRONTEND,
    IS_WINDOWS,
    cyan,
    dim,
    find_npm,
    green,
    red,
    require_setup,
    yellow,
)

API_URL = "http://127.0.0.1:8000"
WEB_URL = "http://127.0.0.1:5173"

_processes: list[subprocess.Popen[str]] = []
_stopping = threading.Event()


def _pump(stream: IO[str], label: str, colour) -> None:
    """Forward one process's output, tagged so you can tell them apart."""
    tag = colour(f"[{label}]")
    for line in iter(stream.readline, ""):
        if _stopping.is_set():
            break
        print(f"{tag} {line.rstrip()}", flush=True)


def _spawn(name: str, cmd: list[str], cwd, colour) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        # A new process group on Windows means Ctrl-C reaches the children rather
        # than only this script.
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0,
    )
    _processes.append(process)
    threading.Thread(target=_pump, args=(process.stdout, name, colour), daemon=True).start()
    return process


def _wait_for_api(timeout_s: int = 45) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _stopping.is_set():
            return False
        # A process that has already exited will never become healthy.
        for process in _processes:
            if process.poll() is not None:
                return False
        try:
            with urllib.request.urlopen(f"{API_URL}/health", timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(0.5)
    return False


def _shutdown(*_: object) -> None:
    if _stopping.is_set():
        return
    _stopping.set()
    print()
    print(yellow("Stopping..."))
    for process in _processes:
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
    for process in _processes:
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()


def _api_checks() -> dict[str, str]:
    """Ask a running API what actually works, via /ready.

    Worth doing when reusing someone else's process: a container built without the
    `market` extra reports itself healthy, and the missing ticker lookup would
    otherwise only show up when you clicked the button.
    """
    try:
        with urllib.request.urlopen(f"{API_URL}/ready", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        checks = payload.get("checks", {})
        return {str(k): str(v) for k, v in checks.items()}
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return {}


def _api_already_running() -> bool:
    """Is something already answering on :8000?

    Most often that is the Docker container. Starting a second API would just fail
    to bind the port, so reuse whatever is there and start only the web app.
    """
    try:
        with urllib.request.urlopen(f"{API_URL}/health", timeout=1.5) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def main() -> int:
    py = require_setup()
    npm = find_npm()
    if npm is None:
        print(red("npm was not found on your PATH."))
        return 1

    signal.signal(signal.SIGINT, _shutdown)

    reuse_api = _api_already_running()

    print()
    if reuse_api:
        print(cyan("An API is already answering on :8000 - reusing it."))
        print(dim("That is usually the Docker container. Starting the web app only."))

        market = _api_checks().get("market_data", "")
        if market and market != "ok":
            print()
            print(yellow(f"  Note: that API reports market data as \"{market}\"."))
            if "not installed" in market:
                print(dim("  Ticker lookup will not work against it. Rebuild the image"))
                print(dim("  (it now includes the client), or stop the container and let"))
                print(dim("  this script run the API itself. Manual entry works either way."))
    else:
        print(cyan("Starting the pricing API and the web app..."))
    print(dim("Ctrl-C stops what this script started."))
    print()

    if not reuse_api:
        _spawn("api", [str(py), "-m", "uvicorn", "api.main:app", "--reload", "--port", "8000"],
               BACKEND, cyan)
    _spawn("web", [npm, "run", "dev"], FRONTEND, green)

    if reuse_api or _wait_for_api():
        print()
        print(green("  Ready."))
        print(f"    App:       {WEB_URL}")
        print(f"    API docs:  {WEB_URL}/api/docs")
        print()
        # Vite needs a moment after the API is up before it will serve the page.
        time.sleep(2)
        try:
            webbrowser.open(WEB_URL)
        except Exception:
            print(dim(f"  Open {WEB_URL} in your browser."))
    else:
        print()
        print(red("  The API did not start. The error should be in the [api] lines above."))

    try:
        while not _stopping.is_set():
            for process in _processes:
                if process.poll() is not None:
                    print(red("\nOne of the processes exited; shutting the other down."))
                    _shutdown()
                    return 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
