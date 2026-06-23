"""nff mcp — launch the MCP server (streamable-HTTP transport)."""

import asyncio

import click


@click.command("mcp")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address")
@click.option("--port", default=3010, type=int, show_default=True, help="Bind port")
def mcp(host, port):
    """Start the nff MCP server (HTTP on host:port/mcp)."""
    from nff import mcp_server
    from nff.tools import daemon

    # `nff init` already starts the server in the background, so a manual `nff mcp`
    # would otherwise crash on the bound port. Bail out cleanly if it's already up.
    if daemon.is_running(host, port):
        click.echo(f"nff MCP server already running on http://{host}:{port}/mcp")
        return
    asyncio.run(mcp_server.run_server(host=host, port=port))
