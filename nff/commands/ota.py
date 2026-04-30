"""nff ota — over-the-air firmware update (Pro feature)."""

from __future__ import annotations

import sys

import click
from rich.console import Console

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)

_PRO_URL = "https://nanoforgeflow.com"


@click.command()
@click.argument("sketch", required=False, metavar="SKETCH")
@click.option("--ip", default=None, metavar="IP_ADDRESS", help="Target device IP address.")
def ota(sketch: str | None, ip: str | None) -> None:
    """Flash firmware over-the-air to a remote device (Pro).

    SKETCH  Path to the sketch directory or .ino file to upload.
    """
    console.print()
    console.print(
        "  [bold red]✗[/bold red]  [bold]nff ota[/bold] requires a [bold]Pro[/bold] subscription."
    )
    console.print()
    console.print("  Over-the-air updates are not available in the free tier.")
    console.print(
        "  Upgrade to [bold]nff Pro[/bold] to flash firmware wirelessly "
        "without a USB connection."
    )
    console.print()
    console.print(
        f"  [bold cyan]{_PRO_URL}[/bold cyan]"
    )
    console.print()
