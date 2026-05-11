"""nff — Claude Code IoT Bridge."""

import os
import sys

__version__ = "0.2.16"


def run() -> None:
    """Console-script entry point: exec the bundled Rust binary when present."""
    _exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nff")
    if sys.platform == "win32":
        _exe += ".exe"
    if os.path.isfile(_exe):
        if sys.platform == "win32":
            import subprocess
            sys.exit(subprocess.call([_exe] + sys.argv[1:]))
        else:
            os.execv(_exe, [_exe] + sys.argv[1:])
    # Binary not bundled (source install / unsupported platform) — fall back to Python CLI.
    from nff.cli import cli
    cli()
