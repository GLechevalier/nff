"""Background lifecycle for the nff MCP server.

The MCP server is an HTTP server (`nff mcp` → uvicorn on 127.0.0.1:3010). Claude Code
connects to it over HTTP but does NOT spawn it, so `nff init` starts it here as a
detached background process. It stays up until the machine reboots or the process is
killed; `nff doctor` detects a down server.
"""

import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

from nff import config

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3010

# Detached background process logs here so a crash is diagnosable.
LOG_PATH = config.CONFIG_DIR / "mcp.log"


def is_running(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """True if a server is listening on the MCP port. A bound port means the server
    is up (and that a fresh `nff mcp` would fail to bind anyway), so this is the
    signal that guards against double-starting. Use `health_ok()` when you need to
    confirm it's specifically *our* server and responding."""
    return _port_open(host, port)


def health_ok(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """True only if our server answers the unauthenticated /health probe with 200.
    Older nff builds predate /health, so prefer is_running() for liveness; this is
    for a stronger 'it's us and it's healthy' confirmation."""
    try:
        with urllib.request.urlopen(  # noqa: S310 — fixed localhost URL
            f"http://{host}:{port}/health", timeout=1.0
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def start_background(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """Start `nff mcp` as a detached background process. No-op (returns True) if it's
    already running. Returns whether the server is up afterwards."""
    if is_running(host, port):
        return True

    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "a", encoding="utf-8")  # noqa: SIM115 — handed to the child

    cmd = [sys.executable, "-m", "nff", "mcp", "--host", host, "--port", str(port)]
    kwargs: dict = {"stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}

    if sys.platform == "win32":
        # DETACHED_PROCESS: no controlling console. CREATE_NO_WINDOW: no flash of a
        # console window. Together the server outlives the `nff init` shell.
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        )
    else:
        kwargs["start_new_session"] = True  # detach from the parent's session
        kwargs["close_fds"] = True

    try:
        subprocess.Popen(cmd, **kwargs)
    except Exception:
        log.close()
        return False

    # Give uvicorn a moment to bind, then confirm.
    for _ in range(30):
        if is_running(host, port):
            return True
        _sleep(0.1)
    return is_running(host, port)


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def log_path() -> Path:
    return LOG_PATH
