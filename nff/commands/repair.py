"""nff repair — send serial/crash output to the diagnosis server."""

import click
import requests

from nff import config
from nff.tools import auth as auth_tools
from nff.tools.serial import serial_read, _resolve_port, _resolve_baud, SerialError


def call_repair(server_url: str, token: str, serial_output: str,
                build_id=None, board=None) -> dict:
    resp = requests.post(
        f"{server_url}/repair",
        headers={"Authorization": f"Bearer {token}"},
        json={"serial_output": serial_output, "build_id": build_id, "board": board},
        timeout=60,
    )
    if resp.status_code == 401:
        raise ValueError("unauthorized (HTTP 401)")
    resp.raise_for_status()
    return resp.json()


@click.command()
@click.option("--serial", "serial_text", default=None, help="Serial output to diagnose")
@click.option("--capture-ms", default=None, type=int, metavar="MS",
              help="Capture serial for N ms then send")
@click.option("--port", default=None)
@click.option("--baud", default=None, type=int)
@click.option("--build-id", default=None)
@click.option("--board", default=None)
@click.option("--server", default=None)
def repair(serial_text, capture_ms, port, baud, build_id, board, server):
    """Send crash/serial output to the diagnosis server and display the diagnosis."""
    cfg = config.get_diagnosis_config()
    server_url = server or cfg.get("server_url", "http://127.0.0.1:8080")
    access_token = cfg.get("access_token")
    refresh_token = cfg.get("refresh_token")

    if not access_token:
        raise click.ClickException("Not authenticated — run `nff auth login`")

    if serial_text is None and capture_ms is not None:
        try:
            p = _resolve_port(port)
            b = _resolve_baud(baud)
        except SerialError as exc:
            raise click.ClickException(str(exc))
        serial_text = serial_read(capture_ms, p, b)

    if not serial_text:
        raise click.ClickException("No serial output — pass --serial or --capture-ms")

    try:
        result = call_repair(server_url, access_token, serial_text, build_id, board)
    except ValueError:
        if not refresh_token:
            config.clear_diagnosis_tokens()
            raise click.ClickException("Session expired — run `nff auth login`")
        try:
            new_tokens = auth_tools.refresh_tokens(server_url, refresh_token)
            config.set_diagnosis_tokens(new_tokens.access_token, new_tokens.refresh_token)
            result = call_repair(server_url, new_tokens.access_token, serial_text, build_id, board)
        except Exception as exc:
            config.clear_diagnosis_tokens()
            raise click.ClickException(f"Session expired — run `nff auth login`: {exc}")
    except Exception as exc:
        raise click.ClickException(str(exc))

    import json
    click.echo(json.dumps(result, indent=2))
