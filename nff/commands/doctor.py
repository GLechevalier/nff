"""nff doctor — dependency and configuration health check."""

from __future__ import annotations

import pathlib
import sys

# Fix sys.path when this file is run directly (`python doctor.py`).
# Python adds commands/ to sys.path, making `nff` unresolvable.
if __name__ == "__main__":
    _pkg_parent = str(pathlib.Path(__file__).resolve().parents[2])
    if _pkg_parent not in sys.path:
        sys.path.insert(0, _pkg_parent)

import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from typing import NamedTuple

import click
from rich.console import Console

# Windows PowerShell defaults to cp1252 which can't encode ✓/✗.
# Reconfigure stdout to UTF-8 before Rich initialises its stream.
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from nff import config as cfg_module
from nff.tools import boards as boards_module
from nff.tools import toolchain
from nff.tools import wokwi as wokwi_module

console = Console(legacy_windows=False)

_CLAUDE_DESKTOP_CONFIG = Path.home() / ".claude" / "claude_desktop_config.json"


class Check(NamedTuple):
    passed: bool
    detail: str             # printed next to ✓ / ✗ / ⚠
    fix: str | None = None  # hint shown when failed
    optional: bool = False  # True → warn with ⚠ instead of failing with ✗


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_python() -> Check:
    v = sys.version_info
    label = f"Python {v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= (3, 10):
        return Check(True, label)
    return Check(False, f"{label} — nff requires Python 3.10+", "Upgrade Python")


def check_arduino_cli() -> Check:
    version = toolchain.arduino_cli_version()
    if version:
        return Check(True, f"{version}  ({toolchain.find_arduino_cli()})")
    return Check(
        False,
        "arduino-cli not found",
        "Install from https://arduino.github.io/arduino-cli",
    )


def check_esptool() -> Check:
    version = toolchain.esptool_version()
    if version:
        loc = toolchain.find_esptool() or "python -m esptool"
        return Check(True, f"{version}  ({loc})")
    return Check(False, "esptool not found", "Run: pip install esptool")


def check_pyserial() -> Check:
    try:
        version = importlib.metadata.version("pyserial")
        return Check(True, f"pyserial {version}")
    except importlib.metadata.PackageNotFoundError:
        return Check(False, "pyserial not installed", "Run: pip install pyserial")


def check_config() -> Check:
    if not cfg_module.exists():
        return Check(False, "Config not found", "Run: nff init")
    try:
        cfg_module.load()
        return Check(True, f"Config found at {cfg_module.CONFIG_PATH}")
    except cfg_module.ConfigError as exc:
        return Check(
            False,
            f"Config unreadable: {exc}",
            f"Fix or delete {cfg_module.CONFIG_PATH}",
        )


def check_device() -> Check:
    """Check that a recognised board is detected and its port is openable.

    This check is optional — Wokwi simulation works without any physical
    hardware, so a missing device is a warning rather than a hard failure.
    """
    # Lazy import — pyserial may not be installed; check_pyserial will flag it.
    try:
        import serial as _serial
    except ImportError:
        return Check(
            False,
            "Cannot check device — pyserial missing",
            "Run: pip install pyserial",
            optional=True,
        )

    devices = boards_module.list_devices()
    if not devices:
        return Check(
            False,
            "No recognised board detected",
            "Plug in a board and run `nff init`  (or use `nff flash --sim` / Wokwi tools without hardware)",
            optional=True,
        )

    device = devices[0]
    label = f"Device detected: {device.board} on {device.port}"
    if device.wokwi_chip:
        label += f"  [sim: {device.wokwi_chip}]"

    try:
        conn = _serial.Serial(device.port, timeout=0.5)
        conn.close()
    except _serial.SerialException as exc:
        fix = f"Port {device.port} is inaccessible: {exc}"
        if platform.system() == "Linux":
            fix += "\n    → Add yourself to the dialout group: sudo usermod -aG dialout $USER"
        return Check(False, f"{label} — port inaccessible", fix, optional=True)

    return Check(True, label)


def check_claude_desktop() -> Check:
    if not _CLAUDE_DESKTOP_CONFIG.exists():
        return Check(False, "Claude Desktop config not found", "Run: nff init")
    try:
        data = json.loads(_CLAUDE_DESKTOP_CONFIG.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return Check(False, f"Claude Desktop config unreadable: {exc}")
    if "nff" not in data.get("mcpServers", {}):
        return Check(
            False,
            "nff not registered in Claude Desktop config",
            "Run: nff init",
        )
    return Check(True, f"Claude Desktop config OK  ({_CLAUDE_DESKTOP_CONFIG})")


def check_wokwi_cli() -> Check:
    """Check that wokwi-cli is installed. Optional — only needed for simulation."""
    version = toolchain.wokwi_cli_version()
    if version:
        loc = toolchain.find_wokwi_cli()
        return Check(True, f"{version}  ({loc})", optional=True)
    return Check(
        False,
        "wokwi-cli not found  (optional — required for --sim and nff wokwi)",
        "Install from https://github.com/wokwi/wokwi-cli",
        optional=True,
    )


def check_wokwi_token() -> Check:
    """Check that a Wokwi CI API token is configured. Optional."""
    import os

    env_token = os.environ.get("WOKWI_CLI_TOKEN")
    if env_token:
        return Check(True, "Wokwi API token configured  (from WOKWI_CLI_TOKEN env)", optional=True)

    try:
        token = wokwi_module._resolve_token()
    except Exception:
        token = None

    if token:
        return Check(True, f"Wokwi API token configured  (from {cfg_module.CONFIG_PATH})", optional=True)

    return Check(
        False,
        "Wokwi API token not configured  (optional — required for simulation)",
        "Set WOKWI_CLI_TOKEN or run: nff wokwi init",
        optional=True,
    )


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------

_CHECKS = [
    check_python,
    check_arduino_cli,
    check_esptool,
    check_pyserial,
    check_config,
    check_device,
    check_claude_desktop,
    check_wokwi_cli,
    check_wokwi_token,
]


@click.command()
def doctor() -> None:
    """Check dependencies, config, and device connectivity."""
    any_failed = False

    for fn in _CHECKS:
        result = fn()
        if result.passed:
            console.print(f"  [bold green]✓[/bold green] {result.detail}")
        elif result.optional:
            console.print(f"  [bold yellow]⚠[/bold yellow] {result.detail}")
            if result.fix:
                console.print(f"    [yellow]→[/yellow] {result.fix}")
        else:
            console.print(f"  [bold red]✗[/bold red] {result.detail}")
            if result.fix:
                console.print(f"    [yellow]→[/yellow] {result.fix}")
            any_failed = True

    if any_failed:
        sys.exit(1)


if __name__ == "__main__":
    doctor()
