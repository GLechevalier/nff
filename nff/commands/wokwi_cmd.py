"""nff wokwi init/run — Wokwi simulation commands."""

import json
from pathlib import Path

import click

from nff import config
from nff.tools import wokwi as wokwi_module


@click.group("wokwi")
def wokwi_cli():
    """Wokwi simulation commands."""


@wokwi_cli.command("init")
@click.option("--board", default=None, help="Board FQBN")
@click.option("--diagram", default=None, type=click.Path(), help="Path to diagram.json")
def wokwi_init(board, diagram):
    """Generate a default diagram.json for the configured board."""
    fqbn = board or config.get_default_device().get("fqbn") or ""
    if not fqbn:
        raise click.ClickException("No board FQBN — pass --board or run `nff init`")
    try:
        d = wokwi_module.generate_diagram(fqbn)
    except wokwi_module.WokwiError as exc:
        raise click.ClickException(str(exc))
    out = Path(diagram) if diagram else Path("diagram.json")
    out.write_text(json.dumps(d, indent=2), encoding="utf-8")
    click.echo(f"Wrote {out}")


@wokwi_cli.command("run")
@click.option("--timeout", default=5000, type=int, metavar="MS")
@click.option("--serial-log", default=None, type=click.Path(), metavar="FILE")
@click.option("--gui", is_flag=True, hidden=True)
def wokwi_run(timeout, serial_log, gui):
    """Run the Wokwi simulation."""
    import subprocess, sys
    from nff.tools.toolchain import find_wokwi_cli
    cli = find_wokwi_cli()
    if not cli:
        raise click.ClickException("wokwi-cli not found — run `nff install-deps`")
    import os
    runner = wokwi_module.WokwiRunner()
    cwd = Path.cwd()
    try:
        result = runner.run(cwd, timeout_ms=timeout)
    except wokwi_module.WokwiError as exc:
        raise click.ClickException(str(exc))
    if result.serial_output:
        click.echo(result.serial_output)
    if serial_log and result.serial_output:
        Path(serial_log).write_text(result.serial_output, encoding="utf-8")
