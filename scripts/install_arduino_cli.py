#!/usr/bin/env python3
"""Install arduino-cli on Windows, macOS, or Linux without admin rights.

Usage:
    python scripts/install_arduino_cli.py
    python scripts/install_arduino_cli.py --force   # overwrite existing
"""

from __future__ import annotations

import pathlib
import sys as _sys

if _sys.platform == "win32" and hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8")

# Allow running directly from the repo without installing nff first.
_pkg_parent = str(pathlib.Path(__file__).resolve().parents[1])
if _pkg_parent not in _sys.path:
    _sys.path.insert(0, _pkg_parent)

from nff.tools.installer import main  # noqa: E402

if __name__ == "__main__":
    main()
