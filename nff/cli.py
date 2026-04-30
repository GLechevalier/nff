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
from nff.commands.wokwi import wokwi        # noqa: E402
from nff.commands.clean import clean        # noqa: E402
from nff.commands.test import test          # noqa: E402
from nff.commands.connect import connect    # noqa: E402
from nff.commands.ota import ota            # noqa: E402

cli.add_command(init)
cli.add_command(flash)
cli.add_command(monitor)
cli.add_command(doctor)
cli.add_command(wokwi)
cli.add_command(clean)
cli.add_command(test)
cli.add_command(connect)
cli.add_command(ota)


@cli.command("install-deps")
@click.option("--force", is_flag=True, help="Reinstall even if already present.")
@click.option("--skip-wokwi", is_flag=True, help="Skip wokwi-cli installation.")
def install_deps(force: bool, skip_wokwi: bool) -> None:
    """Download and install arduino-cli and wokwi-cli.

    arduino-cli is required for all compile/upload operations.
    wokwi-cli is optional — only needed for --sim and nff wokwi commands.
    """
    from nff.tools import installer
    from nff.tools import wokwi_installer

    any_failed = False

    # -- arduino-cli (required) -----------------------------------------------
    console.print("[bold cyan]arduino-cli[/bold cyan]")
    try:
        exe = installer.install(force=force)
        if not installer.verify(exe):
            console.print("  [bold red]✗[/bold red] arduino-cli verification failed.")
            any_failed = True
    except Exception as exc:
        console.print(f"  [bold red]✗[/bold red] {exc}")
        any_failed = True

    console.print()

    # -- wokwi-cli (optional) -------------------------------------------------
    if skip_wokwi:
        console.print("[dim]wokwi-cli skipped (--skip-wokwi)[/dim]")
    else:
        console.print("[bold cyan]wokwi-cli[/bold cyan]  [dim](optional — for --sim and nff wokwi)[/dim]")
        try:
            exe = wokwi_installer.install(force=force)
            if not wokwi_installer.verify(exe):
                console.print(
                    "  [yellow]⚠[/yellow]  wokwi-cli installed but could not be verified.\n"
                    "    Restart your terminal if `wokwi-cli --version` fails."
                )
        except Exception as exc:
            console.print(
                f"  [yellow]⚠[/yellow]  Could not auto-install wokwi-cli: {exc}\n"
                "    Install manually: [bold]npm install -g @wokwi/cli[/bold]  or\n"
                "    download from [bold]https://github.com/wokwi/wokwi-cli/releases[/bold]"
            )

    if any_failed:
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
