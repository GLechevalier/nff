"""nff — entry point that wires all subcommands into one CLI."""

from __future__ import annotations

import sys

import click
from rich.console import Console

from nff import __version__

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, "-V", "--version", prog_name="nff")
def cli() -> None:
    """nff — Claude Code IoT Bridge.

    Connects Claude Code to physical hardware devices via USB.
    Run `nff init` to get started.
    """


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

from nff.commands.init import init          # noqa: E402
from nff.commands.flash import flash        # noqa: E402
from nff.commands.monitor import monitor    # noqa: E402
from nff.commands.doctor import doctor      # noqa: E402

cli.add_command(init)
cli.add_command(flash)
cli.add_command(monitor)
cli.add_command(doctor)


@cli.command("install-deps")
@click.option("--force", is_flag=True, help="Reinstall even if already present.")
def install_deps(force: bool) -> None:
    """Download and install arduino-cli (runs automatically during `nff init`)."""
    from nff.tools import installer
    console.print("[bold cyan]arduino-cli installer[/bold cyan]")
    try:
        exe = installer.install(force=force)
        if not installer.verify(exe):
            raise SystemExit(1)
    except Exception as exc:
        console.print(f"  [bold red]✗[/bold red] {exc}")
        raise SystemExit(1)


@cli.command()
def mcp() -> None:
    """Start the MCP server (stdio). Called automatically by Claude Code."""
    from nff.mcp_server import main as _mcp_main
    _mcp_main()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Setuptools / pipx entry point: ``nff = "nff.cli:main"``."""
    cli()


if __name__ == "__main__":
    main()
