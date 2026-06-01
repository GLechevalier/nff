"""nff init — interactive setup wizard."""

import subprocess
import sys
from pathlib import Path

import click

from nff import config
from nff.tools import boards as boards_module, installer, toolchain

_SIM_BOARDS = [
    ("Arduino Uno",       "arduino:avr:uno"),
    ("Arduino Mega 2560", "arduino:avr:mega"),
    ("Arduino Nano",      "arduino:avr:nano"),
    ("Arduino Leonardo",  "arduino:avr:leonardo"),
    ("ESP32",             "esp32:esp32:esp32"),
    ("ESP8266",           "esp8266:esp8266:generic"),
]


def _register_mcp():
    exe = sys.executable
    try:
        nff_exe = Path(sys.argv[0]).resolve()
        subprocess.run(
            ["claude", "mcp", "add", "--scope", "user", "nff", str(nff_exe), "mcp"],
            check=False,
        )
    except Exception:
        pass


@click.command()
@click.option("--port", default=None)
@click.option("--baud", default=9600, type=int)
@click.option("--force", is_flag=True)
def init(port, baud, force):
    """Interactive setup — detect board and configure nff."""
    click.echo("Welcome to nff init!\n")
    click.echo("  1) Real board (USB)")
    click.echo("  2) Wokwi simulation")
    choice = click.prompt("Select mode", type=click.Choice(["1", "2"]))

    if choice == "1":
        devices = boards_module.list_devices()
        if devices:
            click.echo("\nDetected boards:")
            for i, d in enumerate(devices, 1):
                click.echo(f"  {i}) {d.board} on {d.port}")
            if len(devices) == 1:
                selected = devices[0]
            else:
                idx = click.prompt("Select board", type=int, default=1) - 1
                selected = devices[max(0, min(idx, len(devices) - 1))]
            resolved_port = port or selected.port
            config.set_default_device(resolved_port, selected.board, selected.fqbn, baud)
        else:
            if not port:
                port = click.prompt("No boards detected. Enter port manually")
            board_name = click.prompt("Board name")
            fqbn = click.prompt("Board FQBN (e.g. arduino:avr:uno)")
            config.set_default_device(port, board_name, fqbn, baud)

        if not toolchain.find_arduino_cli():
            click.echo("\narduino-cli not found — installing…")
            try:
                installer.install()
            except Exception as exc:
                click.echo(f"Warning: could not install arduino-cli: {exc}")

    else:
        click.echo("\nAvailable boards:")
        for i, (name, fqbn) in enumerate(_SIM_BOARDS, 1):
            click.echo(f"  {i}) {name} ({fqbn})")
        idx = click.prompt("Select board", type=int, default=5) - 1
        name, fqbn = _SIM_BOARDS[max(0, min(idx, len(_SIM_BOARDS) - 1))]
        config.set_default_device("", name, fqbn, 9600)

    _register_mcp()
    click.echo("\n✓ nff configured! Run `nff doctor` to verify your setup.")
