"""nff — Claude Code IoT Bridge."""

import os
import sys

__version__ = "0.2.16"


def run() -> None:
    """Console-script entry point: exec the bundled Rust binary."""
    _pkg = os.path.dirname(os.path.abspath(__file__))
    # Wheel install: binary bundled alongside __init__.py
    _exe = os.path.join(_pkg, "nff")
    if sys.platform == "win32":
        _exe += ".exe"
    # Editable dev install: binary in nff-rs/target/release/
    if not os.path.isfile(_exe):
        _exe = os.path.join(os.path.dirname(_pkg), "nff-rs", "target", "release", "nff")
        if sys.platform == "win32":
            _exe += ".exe"
    if os.path.isfile(_exe):
        if sys.platform == "win32":
            import subprocess
            sys.exit(subprocess.call([_exe] + sys.argv[1:]))
        else:
            os.execv(_exe, [_exe] + sys.argv[1:])
    print("error: nff binary not found. Please reinstall nff.", file=sys.stderr)
    sys.exit(1)
