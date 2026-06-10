"""nff mcp — launch the MCP server (streamable-HTTP transport)."""

import asyncio

import click


@click.command("mcp")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address")
@click.option("--port", default=3001, type=int, show_default=True, help="Bind port")
def mcp(host, port):
    """Start the nff MCP server (HTTP on host:port/mcp)."""
    from nff import mcp_server
    asyncio.run(mcp_server.run_server(host=host, port=port))
