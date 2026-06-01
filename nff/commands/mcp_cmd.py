"""nff mcp — launch the MCP server (stdio transport)."""

import asyncio

import click


@click.command("mcp")
@click.option("--host", default="127.0.0.1", hidden=True)
@click.option("--port", default=3000, type=int, hidden=True)
def mcp(host, port):
    """Start the nff MCP server on stdio."""
    from nff import mcp_server
    asyncio.run(mcp_server.run_server())
