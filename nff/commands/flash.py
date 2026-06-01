"""nff flash — compile and upload a sketch."""

import click
from rich.console import Console

from nff import config
from nff.tools import boards as boards_module, toolchain, wokwi as wokwi_module

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
    """Compile and flash a sketch to the device (or simulate with --sim)."""
    import pathlib
    sketch_path = pathlib.Path(file)
    code = sketch_path.read_text(encoding="utf-8")

    # Resolve FQBN
    fqbn = board
    if not fqbn:
        fqbn = config.get_default_device().get("fqbn") or ""
    if not fqbn:
        raise click.ClickException("No board FQBN — pass --board or run `nff init`")

    if sim:
        runner = wokwi_module.WokwiRunner()
        import tempfile, json
        from pathlib import Path
        sketch_dir = toolchain.write_sketch(code)
        console.print("[bold]Compiling…[/bold]")
        compile_result = toolchain.compile_sketch(sketch_dir, fqbn)
        if not compile_result.success:
            raise click.ClickException(f"Compile failed:\n{compile_result.output}")
        elf = toolchain.locate_compiled_elf(sketch_dir, fqbn)
        diagram = wokwi_module.generate_diagram(fqbn)
        (sketch_dir / "diagram.json").write_text(
            json.dumps(diagram, indent=2), encoding="utf-8"
        )
        wokwi_module.write_wokwi_toml(sketch_dir, elf)
        console.print("[bold]Simulating…[/bold]")
        result = runner.run(sketch_dir, timeout_ms=sim_timeout, elf=elf)
        if result.serial_output:
            click.echo(result.serial_output)
        return

    # Resolve port
    resolved_port = port or config.get_default_device().get("port") or ""
    if not resolved_port:
        detected = boards_module.find_device()
        if detected:
            resolved_port = detected.port
    if not resolved_port:
        raise click.ClickException("No port — pass --port or run `nff init`")

    if manual_reset:
        click.pause("Press Enter after manually resetting the board…")

    sketch_dir = toolchain.write_sketch(code)

    console.print("[bold]Compiling…[/bold]")
    for line in toolchain.stream_compile(sketch_dir, fqbn):
        click.echo(line)

    console.print("[bold]Uploading…[/bold]")
    stream = toolchain.stream_upload(sketch_dir, fqbn, resolved_port)
    for line in stream:
        click.echo(line)
    if stream.returncode and stream.returncode != 0:
        raise click.ClickException("Upload failed")
    console.print("[green]Flash complete[/green]")
