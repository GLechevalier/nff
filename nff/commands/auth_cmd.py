"""nff auth login/logout/status."""

import click

from nff import config
from nff.tools import auth as auth_tools


@click.group("auth")
def auth_cli():
    """Manage nff diagnosis server authentication."""


@auth_cli.command("login")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.option("--server", default=None)
def login(email, password, server):
    """Log in to the nff diagnosis server."""
    cfg = config.get_diagnosis_config()
    server_url = server or cfg.get("server_url", "http://127.0.0.1:8080")

    if email and password:
        try:
            tokens = auth_tools.direct_login(server_url, email, password)
        except Exception as exc:
            raise click.ClickException(str(exc))
    elif email is None and password is None:
        try:
            sock, port = auth_tools.bind_callback_server()
        except Exception as exc:
            raise click.ClickException(f"Could not bind callback server: {exc}")
        callback_url = f"http://127.0.0.1:{port}/callback"
        portal_url = f"{server_url}/auth/portal?cb={auth_tools.percent_encode(callback_url)}"
        click.echo(f"Opening browser: {portal_url}")
        try:
            auth_tools.open_browser(portal_url)
        except Exception:
            click.echo(f"Visit manually: {portal_url}")
        try:
            tokens = auth_tools.wait_for_callback(sock, 300)
        except TimeoutError as exc:
            raise click.ClickException(str(exc))
    else:
        raise click.ClickException("Provide both --email and --password, or neither for browser login")

    config.set_diagnosis_tokens(tokens.access_token, tokens.refresh_token)
    click.echo("OK: authenticated")


@auth_cli.command("logout")
@click.option("--server", default=None)
def logout(server):
    """Log out from the nff diagnosis server."""
    import requests as _requests
    cfg = config.get_diagnosis_config()
    server_url = server or cfg.get("server_url", "http://127.0.0.1:8080")
    token = cfg.get("access_token")
    if token:
        try:
            _requests.post(
                f"{server_url}/api/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
        except Exception:
            pass
    config.clear_diagnosis_tokens()
    config.clear_mcp_tokens()
    click.echo("OK: logged out")


@auth_cli.command("status")
def status():
    """Show authentication status."""
    cfg = config.get_diagnosis_config()
    if cfg.get("access_token"):
        click.echo("OK: authenticated")
    else:
        click.echo("ERROR: not authenticated — run `nff auth login`")
