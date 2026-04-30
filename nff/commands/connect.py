"""nff connect — remote device connection (Pro feature)."""

from __future__ import annotations

import sys

import click
from rich.console import Console

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)

_PRO_URL = "https://nanoforgeflow.com"


@click.command()
@click.argument("ip_address")
def connect(ip_address: str) -> None:
    """Connect to a remote device over the network (Pro).

    IP_ADDRESS  IP address of the remote device, e.g. 192.168.1.42
    """
    console.print()
    console.print(
        "  [bold red]✗[/bold red]  [bold]nff connect[/bold] requires a [bold]Pro[/bold] subscription."
    )
    console.print()
    console.print("  Remote device connectivity is not available in the free tier.")
    console.print(
        f"  Upgrade to [bold]nff Pro[/bold] to connect to [bold]{ip_address}[/bold] "
        "and manage devices over the network."
    )
    console.print()
    console.print("  Visit the link below to upgrade and unlock remote access:")
    console.print(
        f"  [bold cyan]{_PRO_URL}[/bold cyan]  [dim]← pay & upgrade here[/dim]"
    )
    console.print()
