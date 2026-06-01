"""nff monitor — stream serial output."""

import click

from nff.tools.serial import _resolve_baud, _resolve_port, stream_lines, SerialError


@click.command()
@click.option("--port", default=None)
@click.option("--baud", default=None, type=int)
@click.option("--timeout", default=None, type=float, metavar="SECONDS")
def monitor(port, baud, timeout):
    """Stream serial output from the device."""
    try:
        p = _resolve_port(port)
        b = _resolve_baud(baud)
    except SerialError as exc:
        raise click.ClickException(str(exc))
    try:
        for line in stream_lines(p, b, timeout_s=timeout):
            click.echo(line)
    except KeyboardInterrupt:
        pass
