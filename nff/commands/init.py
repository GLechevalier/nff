"""nff init — detect board, write config, register the MCP server."""

from __future__ import annotations

import pathlib
import sys

if __name__ == "__main__":
    _pkg_parent = str(pathlib.Path(__file__).resolve().parents[2])
    if _pkg_parent not in sys.path:
        sys.path.insert(0, _pkg_parent)

import json
from pathlib import Path

import click
from rich.console import Console

from nff import config as cfg_module
from nff.tools import boards as boards_module
from nff.tools import toolchain
from nff.tools import installer
from nff.tools.boards import DetectedDevice

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)

_CLAUDE_DESKTOP_CONFIG = Path.home() / ".claude" / "claude_desktop_config.json"
_MCP_ENTRY: dict = {"command": "nff", "args": ["mcp"]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_arduino_cli() -> None:
    """Install arduino-cli silently if it is not already on PATH."""
    if toolchain.find_arduino_cli():
        return
    console.print(
        "  [yellow]⚠[/yellow]  arduino-cli not found — installing automatically…"
    )
    try:
        exe = installer.install(force=False)
        if installer.verify(exe):
            console.print("  [bold green]✓[/bold green] arduino-cli installed.")
        else:
            console.print(
                "  [yellow]⚠[/yellow]  arduino-cli installed but could not be verified. "
                "Restart your terminal if commands fail."
            )
    except Exception as exc:
        console.print(
            f"  [yellow]⚠[/yellow]  Could not auto-install arduino-cli: {exc}\n"
            "  Install manually: https://arduino.github.io/arduino-cli"
        )


def _pick_device(devices: list[DetectedDevice]) -> DetectedDevice:
    """Return the chosen device; prompts when more than one is connected."""
    if len(devices) == 1:
        return devices[0]

    console.print("\n[bold]Multiple boards detected:[/bold]")
    for i, d in enumerate(devices, 1):
        console.print(f"  {i}. [bold]{d.board}[/bold] on {d.port}")

    choice = click.prompt(
        "Select board",
        type=click.IntRange(1, len(devices)),
        default=1,
    )
    return devices[choice - 1]


def _update_claude_desktop_config() -> None:
    """Merge the nff MCP entry into ~/.claude/claude_desktop_config.json.

    Preserves all pre-existing keys and other mcpServers entries.

    Raises:
        OSError: If the file cannot be written.
        ValueError: If an existing file contains invalid JSON (caller should
            surface this as a warning rather than aborting).
    """
    _CLAUDE_DESKTOP_CONFIG.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if _CLAUDE_DESKTOP_CONFIG.exists():
        raw = _CLAUDE_DESKTOP_CONFIG.read_text(encoding="utf-8")
        if raw.strip():
            data = json.loads(raw)  # raises ValueError on bad JSON

    data.setdefault("mcpServers", {})["nff"] = _MCP_ENTRY

    _CLAUDE_DESKTOP_CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------

@click.command()
@click.option("--port", default=None, metavar="PORT",
              help="Serial port to use; skips auto-detection.")
@click.option("--baud", default=9600, show_default=True,
              help="Baud rate stored in config.")
@click.option("--force", is_flag=True,
              help="Overwrite an existing config without prompting.")
def init(port: str | None, baud: int, force: bool) -> None:
    """Detect a connected board, write config, and register the MCP server."""
    _ensure_arduino_cli()

    # Guard against overwriting an existing, valid config
    if cfg_module.exists() and not force:
        try:
            existing = cfg_module.get_default_device()
            if existing.get("port"):
                console.print(
                    f"[yellow]Config already exists[/yellow] "
                    f"({existing.get('board', '?')} on {existing['port']}).\n"
                    "  Pass [bold]--force[/bold] to overwrite."
                )
                return
        except cfg_module.ConfigError:
            pass  # unreadable config → let the user fix it by re-running init

    # -----------------------------------------------------------------
    # Device resolution
    # -----------------------------------------------------------------
    device: DetectedDevice | None = None

    if port:
        # User supplied a port — accept it even if the board isn't recognised.
        console.print(f"  Using specified port [bold]{port}[/bold]…")
        device = boards_module.find_device(port)
        if device is None:
            console.print(
                f"  [yellow]⚠[/yellow]  {port} not matched to a known board. "
                "Storing as 'Unknown'."
            )
            cfg_module.set_default_device(port=port, board="Unknown", fqbn="", baud=baud)
            _write_success(port=port, board="Unknown", device=None)
            return
    else:
        console.print("  Scanning USB ports…")
        devices = boards_module.list_devices()

        if not devices:
            console.print(
                "[bold red]✗[/bold red] No recognised boards found.\n"
                "  Plug in a board and try again, or use "
                "[bold]--port PORT[/bold] to specify one manually."
            )
            sys.exit(1)

        device = _pick_device(devices)

    # -----------------------------------------------------------------
    # Write nff config
    # -----------------------------------------------------------------
    cfg_module.set_default_device(
        port=device.port,
        board=device.board,
        fqbn=device.fqbn,
        baud=baud,
    )

    _write_success(port=device.port, board=device.board, device=device)


def _write_success(port: str, board: str, device: DetectedDevice | None) -> None:
    """Print the success lines and update the Claude Desktop config."""
    if device:
        console.print(
            f"  [bold green]✓[/bold green] Found: [bold]{device.board}[/bold] "
            f"on {device.port} "
            f"(vendor: {device.vendor_id}, product: {device.product_id})"
        )

    console.print(
        f"  [bold green]✓[/bold green] Config written to "
        f"[bold]{cfg_module.CONFIG_PATH}[/bold]"
    )

    try:
        _update_claude_desktop_config()
        console.print(
            f"  [bold green]✓[/bold green] MCP config written to "
            f"[bold]{_CLAUDE_DESKTOP_CONFIG}[/bold]"
        )
    except ValueError as exc:
        console.print(
            f"  [yellow]⚠[/yellow]  Claude Desktop config has invalid JSON — "
            f"fix it manually: {exc}\n"
            f"  Path: {_CLAUDE_DESKTOP_CONFIG}"
        )
    except OSError as exc:
        console.print(
            f"  [yellow]⚠[/yellow]  Could not write Claude Desktop config: {exc}"
        )


if __name__ == "__main__":
    init()
