"""nff flash — compile and upload a sketch (or simulate with --sim)."""

import json
import pathlib

import click
from rich.console import Console

from nff import config
from nff.tools import (
    arduino_lib,
    boards as boards_module,
    toolchain,
    wokwi as wokwi_module,
)

console = Console()


@click.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--board", default=None, help="Board FQBN")
@click.option("--port", default=None, help="Serial port")
@click.option("--baud", default=None, type=int)
@click.option("--manual-reset", is_flag=True)
@click.option("--sim", is_flag=True, help="Run in Wokwi simulator instead of hardware")
@click.option("--sim-timeout", default=5000, type=int, metavar="MS")
def flash(file, board, port, baud, manual_reset, sim, sim_timeout):
    """Compile and flash a sketch to the device (or simulate with --sim).

    FILE may be a .ino file or a sketch folder. To only check that a sketch
    builds (no board needed), use `nff compile` instead.
    """
    # Resolve FQBN
    fqbn = board or config.get_default_device().get("fqbn") or ""
    if not fqbn:
        raise click.ClickException("No board FQBN — pass --board or run `nff init`")

    # Normalise the sketch into a compilable folder (handles .ino files and dirs).
    try:
        sketch_dir = toolchain.resolve_sketch_dir(source=pathlib.Path(file))
    except toolchain.ToolchainError as exc:
        raise click.ClickException(str(exc))

    if sim:
        console.print("[bold]Compiling…[/bold]")
        result = toolchain.compile_only(fqbn, source=pathlib.Path(file))
        if not result.ok:
            raise click.ClickException(f"Compile failed:\n{result.output}")
        elf = result.elf
        diagram = wokwi_module.generate_diagram(fqbn)
        (sketch_dir / "diagram.json").write_text(
            json.dumps(diagram, indent=2), encoding="utf-8"
        )
        wokwi_module.write_wokwi_toml(sketch_dir, elf, firmware_path=result.image)
        console.print("[bold]Simulating…[/bold]")
        runner = wokwi_module.WokwiRunner()
        sim_result = runner.run(sketch_dir, timeout_ms=sim_timeout, elf=elf)
        if sim_result.serial_output:
            click.echo(sim_result.serial_output)
        return

    # Resolve port (hardware path only)
    resolved_port = port or config.get_default_device().get("port") or ""
    if not resolved_port:
        detected = boards_module.find_device()
        if detected:
            resolved_port = detected.port
    if not resolved_port:
        raise click.ClickException("No port — pass --port or run `nff init`")

    if manual_reset:
        click.pause("Press Enter after manually resetting the board…")

    # Non-blocking: warn if a local nff-sdk-c checkout is newer than the synced
    # Arduino library, so "flash to test the fix" never silently builds old code.
    warn = arduino_lib.local_sdk_newer_than_synced()
    if warn:
        console.print(f"[yellow]warning:[/yellow] {warn}")

    console.print("[bold]Compiling…[/bold]")
    rc = toolchain.stream_with_retry(
        lambda: toolchain.stream_compile(sketch_dir, fqbn), click.echo
    )
    if rc != 0:
        raise click.ClickException("Compile failed")

    console.print("[bold]Uploading…[/bold]")
    rc = toolchain.stream_with_retry(
        lambda: toolchain.stream_upload(sketch_dir, fqbn, resolved_port),
        click.echo,
        backoff=(2.0, 4.0),
    )
    if rc != 0:
        raise click.ClickException("Upload failed")
    console.print("[green]Flash complete[/green]")
