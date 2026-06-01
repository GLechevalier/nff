"""nff doctor — dependency and environment checks."""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import click
import serial

import nff.tools.boards as boards_module
from nff import config
from nff.tools import toolchain

_CLAUDE_DESKTOP_CONFIG = Path.home() / ".claude" / "claude_desktop_config.json"


@dataclass
class Check:
    passed: bool
    detail: str
    fix: Optional[str] = None
    optional: bool = False


def check_python() -> Check:
    vi = sys.version_info
    if vi.major >= 3 and vi.minor >= 10:
        return Check(passed=True, detail=f"Python {vi.major}.{vi.minor}.{vi.micro}")
    return Check(
        passed=False,
        detail=f"Python {vi.major}.{vi.minor} (need 3.10+)",
        fix="Install Python 3.10 or newer from python.org",
    )


def check_arduino_cli() -> Check:
    ver = toolchain.arduino_cli_version()
    if ver:
        return Check(passed=True, detail=ver)
    return Check(
        passed=False,
        detail="arduino-cli not found",
        fix="Run `nff install-deps` to install arduino-cli",
    )


def check_esptool() -> Check:
    ver = toolchain.esptool_version()
    if ver:
        return Check(passed=True, detail=ver)
    return Check(
        passed=False,
        detail="esptool not found",
        fix="Run `pip install esptool`",
        optional=True,
    )


def check_pyserial() -> Check:
    try:
        import serial as _s
        ver = getattr(_s, "__version__", "unknown")
        return Check(passed=True, detail=f"pyserial {ver}")
    except ImportError:
        return Check(passed=False, detail="pyserial not installed",
                     fix="Run `pip install pyserial`")


def check_config() -> Check:
    try:
        if not config.exists():
            return Check(passed=False, detail="~/.nff/config.json not found",
                         fix="Run `nff init` to create config")
        config.load()
        return Check(passed=True, detail=str(config.CONFIG_PATH))
    except config.ConfigError as exc:
        return Check(passed=False, detail=str(exc), fix="Run `nff init` to recreate config")


def check_device() -> Check:
    devices = boards_module.list_devices()
    if not devices:
        return Check(passed=False, detail="No known boards detected",
                     fix="Connect a supported board via USB")
    d = devices[0]
    try:
        conn = serial.Serial(d.port, timeout=1)
        conn.close()
        return Check(passed=True, detail=f"{d.board} on {d.port}")
    except serial.SerialException as exc:
        return Check(passed=False, detail=f"{d.board} on {d.port}: {exc}",
                     fix="Close other applications using the serial port")


def check_claude_desktop() -> Check:
    path = _CLAUDE_DESKTOP_CONFIG
    if not path.exists():
        return Check(passed=False, detail=f"{path} not found",
                     fix="Run `nff init` to register nff as an MCP server", optional=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Check(passed=False, detail=f"{path} is not valid JSON", optional=True)
    if "nff" in data.get("mcpServers", {}):
        return Check(passed=True, detail="nff registered in claude_desktop_config.json")
    return Check(passed=False, detail="nff not found in mcpServers",
                 fix="Run `nff init` to register nff", optional=True)


@click.command()
def doctor():
    """Check that all nff dependencies are installed and configured."""
    checks = [
        ("Python", check_python()),
        ("arduino-cli", check_arduino_cli()),
        ("esptool", check_esptool()),
        ("pyserial", check_pyserial()),
        ("Config", check_config()),
        ("Device", check_device()),
        ("Claude Desktop", check_claude_desktop()),
    ]
    any_failed = False
    for name, ch in checks:
        icon = "✓" if ch.passed else ("?" if ch.optional else "✗")
        click.echo(f"  [{icon}] {name}: {ch.detail}")
        if not ch.passed and ch.fix:
            click.echo(f"        → {ch.fix}")
        if not ch.passed and not ch.optional:
            any_failed = True
    if any_failed:
        raise SystemExit(1)
