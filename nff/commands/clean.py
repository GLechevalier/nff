"""nff clean — remove the MCP server registration and optionally the nff config."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console

from nff import config as cfg_module

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)

_CLAUDE_DESKTOP_CONFIG = Path.home() / ".claude" / "claude_desktop_config.json"


def _remove_from_claude_code() -> bool:
    """Run `claude mcp remove nff`. Returns True on success."""
    if not shutil.which("claude"):
        return False
    try:
        result = subprocess.run(
            ["claude", "mcp", "remove", "nff"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _remove_from_claude_desktop_config() -> bool:
    """Remove the nff mcpServers entry from claude_desktop_config.json.

    Returns True if the entry was present and removed, False if it wasn't there.
    """
    if not _CLAUDE_DESKTOP_CONFIG.exists():
        return False

    raw = _CLAUDE_DESKTOP_CONFIG.read_text(encoding="utf-8")
    if not raw.strip():
        return False

    data: dict = json.loads(raw)
    servers: dict = data.get("mcpServers", {})
    if "nff" not in servers:
        return False

    del servers["nff"]
    if not servers:
        data.pop("mcpServers", None)

    _CLAUDE_DESKTOP_CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


@click.command()
@click.option(
    "--config",
    "remove_config",
    is_flag=True,
    help="Also delete ~/.nff/config.json.",
)
def clean(remove_config: bool) -> None:
    """Remove the nff MCP server registration from Claude Code and Claude Desktop."""
    any_removed = False

    # Claude Code CLI
    if _remove_from_claude_code():
        console.print(
            "  [bold green]✓[/bold green] Removed from Claude Code "
            "([bold]claude mcp remove nff[/bold])"
        )
        any_removed = True
    else:
        console.print(
            "  [dim]`claude` CLI not found or nff was not registered — skipping.[/dim]"
        )

    # Claude Desktop JSON config
    try:
        removed = _remove_from_claude_desktop_config()
        if removed:
            console.print(
                f"  [bold green]✓[/bold green] Removed nff entry from "
                f"[bold]{_CLAUDE_DESKTOP_CONFIG}[/bold]"
            )
            any_removed = True
        else:
            console.print(
                f"  [dim]nff not found in {_CLAUDE_DESKTOP_CONFIG} — nothing to remove.[/dim]"
            )
    except (ValueError, OSError) as exc:
        console.print(f"  [yellow]⚠[/yellow]  Could not update Claude Desktop config: {exc}")

    # Optional: nff config file
    if remove_config:
        config_path = cfg_module.CONFIG_PATH
        if config_path.exists():
            config_path.unlink()
            console.print(
                f"  [bold green]✓[/bold green] Deleted [bold]{config_path}[/bold]"
            )
            any_removed = True
        else:
            console.print(f"  [dim]{config_path} does not exist — nothing to delete.[/dim]")

    if not any_removed:
        console.print("  Nothing to clean.")
