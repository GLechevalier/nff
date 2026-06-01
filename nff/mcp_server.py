"""nff MCP server — streamable-HTTP transport using the Python mcp library."""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any, Optional

import uvicorn
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.routing import Mount

import nff.tools.boards as boards_module
import nff.tools.serial as serial_module
import nff.tools.toolchain as toolchain
import nff.tools.wokwi as wokwi_module
from nff import config
from nff.tools.wokwi import WokwiError

# ---------------------------------------------------------------------------
# Resolver helpers (tested directly)
# ---------------------------------------------------------------------------


def _resolve_port(port: Optional[str]) -> str:
    if port:
        return port
    p = config.get_default_device().get("port")
    if p:
        return p
    raise ValueError("No port configured — pass port= or run `nff init`")


def _resolve_fqbn_and_port(board: Optional[str], port: Optional[str]) -> tuple[str, str]:
    fqbn = board or config.get_default_device().get("fqbn") or ""
    resolved_port = port or config.get_default_device().get("port") or ""
    if not fqbn or not resolved_port:
        raise ValueError("Missing board FQBN or port — pass them explicitly or run `nff init`")
    return fqbn, resolved_port


# ---------------------------------------------------------------------------
# Async MCP tool handlers
# ---------------------------------------------------------------------------


async def list_devices() -> dict:
    devices = boards_module.list_devices()
    return {
        "devices": [
            {
                "port": d.port,
                "board": d.board,
                "fqbn": d.fqbn,
                "vendor_id": d.vendor_id,
                "product_id": d.product_id,
                "wokwi_chip": d.wokwi_chip,
            }
            for d in devices
        ]
    }


async def flash(
    code: str,
    board: Optional[str] = None,
    port: Optional[str] = None,
) -> str:
    try:
        fqbn, resolved_port = _resolve_fqbn_and_port(board, port)
    except ValueError as exc:
        return f"ERROR: {exc}"
    return toolchain.flash(code, fqbn, resolved_port)


async def serial_read(
    duration_ms: int = 3000,
    port: Optional[str] = None,
    baud: Optional[int] = None,
) -> str:
    return serial_module.serial_read(duration_ms, port, baud)


async def serial_write(
    data: str,
    port: Optional[str] = None,
    baud: Optional[int] = None,
) -> str:
    return serial_module.serial_write(data, port, baud)


async def reset_device(port: Optional[str] = None) -> str:
    return serial_module.reset_device(port)


async def get_device_info(port: Optional[str] = None) -> dict:
    try:
        p = _resolve_port(port)
    except ValueError as exc:
        return {"error": str(exc)}
    device = boards_module.find_device(p)
    baud = config.get_default_device().get("baud", 9600)
    if device:
        return {
            "port": device.port,
            "board": device.board,
            "fqbn": device.fqbn,
            "baud": baud,
            "vendor_id": device.vendor_id,
            "product_id": device.product_id,
            "wokwi_chip": device.wokwi_chip,
        }
    cfg = config.get_default_device()
    return {
        "port": p,
        "board": cfg.get("board") or "Unknown",
        "fqbn": cfg.get("fqbn") or "",
        "baud": baud,
        "vendor_id": "",
        "product_id": "",
        "wokwi_chip": None,
    }


async def wokwi_flash(
    code: str,
    board: Optional[str] = None,
    timeout_ms: int = 5000,
) -> dict:
    fqbn = board or config.get_default_device().get("fqbn") or ""
    if not fqbn:
        return {"serial_output": "", "compile_output": "ERROR: Missing board FQBN",
                "exit_code": 1, "simulated": True}
    try:
        compile_output, elf_path = toolchain.compile(code, fqbn)
    except Exception as exc:
        return {"serial_output": "", "compile_output": f"compile error: {exc}",
                "exit_code": 1, "simulated": True}
    runner = wokwi_module.WokwiRunner()
    try:
        from pathlib import Path
        from nff.tools import toolchain as tc
        sd = Path(tc._SKETCH_DIR)
        sd.mkdir(parents=True, exist_ok=True)
        diagram = wokwi_module.generate_diagram(fqbn)
        (sd / "diagram.json").write_text(json.dumps(diagram, indent=2), encoding="utf-8")
        wokwi_module.write_wokwi_toml(sd, elf_path)
        result = runner.run(sd, timeout_ms=timeout_ms, elf=elf_path)
    except WokwiError as exc:
        return {"serial_output": "", "compile_output": compile_output,
                "exit_code": 1, "simulated": True, "wokwi_error": str(exc)}
    except Exception as exc:
        return {"serial_output": "", "compile_output": compile_output,
                "exit_code": 1, "simulated": True, "error": str(exc)}
    return {
        "serial_output": result.serial_output,
        "compile_output": compile_output,
        "exit_code": result.exit_code,
        "simulated": True,
    }


async def wokwi_serial_read(
    code: str,
    board: Optional[str] = None,
    duration_ms: int = 3000,
) -> str:
    fqbn = board or config.get_default_device().get("fqbn") or ""
    if not fqbn:
        return "ERROR: Missing board FQBN"
    try:
        compile_output, elf_path = toolchain.compile(code, fqbn)
    except Exception as exc:
        return f"ERROR: compile failed: {exc}"
    runner = wokwi_module.WokwiRunner()
    try:
        from pathlib import Path
        from nff.tools import toolchain as tc
        sd = Path(tc._SKETCH_DIR)
        sd.mkdir(parents=True, exist_ok=True)
        diagram = wokwi_module.generate_diagram(fqbn)
        (sd / "diagram.json").write_text(json.dumps(diagram, indent=2), encoding="utf-8")
        wokwi_module.write_wokwi_toml(sd, elf_path)
        result = runner.run(sd, timeout_ms=duration_ms, elf=elf_path)
    except WokwiError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR: {exc}"
    return result.serial_output


async def wokwi_get_diagram(board: str) -> str:
    try:
        diagram = wokwi_module.generate_diagram(board)
        return json.dumps(diagram, indent=2)
    except WokwiError as exc:
        return f"ERROR: {exc}"


async def authenticate(
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    from nff.tools import auth as auth_tools
    cfg = config.get_diagnosis_config()
    server_url = cfg.get("server_url", "http://127.0.0.1:8080")
    if email and password:
        try:
            tokens = auth_tools.direct_login(server_url, email, password)
        except Exception as exc:
            return f"ERROR: {exc}"
    elif email is None and password is None:
        try:
            sock, port = auth_tools.bind_callback_server()
            callback_url = f"http://127.0.0.1:{port}/callback"
            portal_url = f"{server_url}/auth/portal?cb={auth_tools.percent_encode(callback_url)}"
            try:
                auth_tools.open_browser(portal_url)
            except Exception:
                pass
            tokens = auth_tools.wait_for_callback(sock, 300)
        except Exception as exc:
            return f"ERROR: {exc}"
    else:
        return "ERROR: provide both email and password, or neither for browser login"
    try:
        config.set_diagnosis_tokens(tokens.access_token, tokens.refresh_token)
    except Exception as exc:
        return f"ERROR: could not save tokens: {exc}"
    return "OK: authenticated"


async def auth_logout() -> str:
    import requests as _requests
    cfg = config.get_diagnosis_config()
    server_url = cfg.get("server_url", "http://127.0.0.1:8080")
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
    try:
        config.clear_diagnosis_tokens()
    except Exception as exc:
        return f"ERROR: {exc}"
    return "OK: logged out"


async def auth_status() -> str:
    try:
        cfg = config.get_diagnosis_config()
    except Exception as exc:
        return f"ERROR: {exc}"
    if cfg.get("access_token"):
        return "OK: authenticated"
    return "ERROR: not authenticated — run `nff auth login`"


async def repair(
    serial_output: str,
    build_id: Optional[str] = None,
    board: Optional[str] = None,
) -> str:
    import requests as _requests
    from nff.tools import auth as auth_tools
    from nff.commands.repair import call_repair
    cfg = config.get_diagnosis_config()
    server_url = cfg.get("server_url", "http://127.0.0.1:8080")
    access_token = cfg.get("access_token")
    refresh_token = cfg.get("refresh_token")
    if not access_token:
        return "ERROR: not authenticated — run `nff auth login`"
    try:
        result = call_repair(server_url, access_token, serial_output, build_id, board)
        return json.dumps(result)
    except ValueError:
        if not refresh_token:
            config.clear_diagnosis_tokens()
            return "ERROR: session expired — run `nff auth login`"
        try:
            new_tokens = auth_tools.refresh_tokens(server_url, refresh_token)
            config.set_diagnosis_tokens(new_tokens.access_token, new_tokens.refresh_token)
            result = call_repair(server_url, new_tokens.access_token, serial_output, build_id, board)
            return json.dumps(result)
        except Exception:
            config.clear_diagnosis_tokens()
            return "ERROR: session expired — run `nff auth login` to re-authenticate"
    except Exception as exc:
        return f"ERROR: {exc}"


# ---------------------------------------------------------------------------
# MCP server wiring
# ---------------------------------------------------------------------------

app = Server("nff")

_TOOLS = [
    Tool(name="list_devices", description="List all connected USB/serial devices with board identification",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="flash", description="Compile and upload an Arduino/ESP sketch to the connected board",
         inputSchema={"type": "object", "properties": {
             "code": {"type": "string"}, "board": {"type": "string"}, "port": {"type": "string"}},
             "required": ["code"]}),
    Tool(name="serial_read", description="Capture serial output from the device for a given duration",
         inputSchema={"type": "object", "properties": {
             "duration_ms": {"type": "integer", "default": 3000},
             "port": {"type": "string"}, "baud": {"type": "integer"}}}),
    Tool(name="serial_write", description="Send a string to the device over serial",
         inputSchema={"type": "object", "properties": {
             "data": {"type": "string"}, "port": {"type": "string"}, "baud": {"type": "integer"}},
             "required": ["data"]}),
    Tool(name="reset_device", description="Toggle DTR to hardware-reset the board",
         inputSchema={"type": "object", "properties": {"port": {"type": "string"}}}),
    Tool(name="get_device_info", description="Return detailed information about the connected device as JSON",
         inputSchema={"type": "object", "properties": {"port": {"type": "string"}}}),
    Tool(name="wokwi_flash", description="Compile a sketch and run it in the Wokwi simulator",
         inputSchema={"type": "object", "properties": {
             "code": {"type": "string"}, "board": {"type": "string"},
             "timeout_ms": {"type": "integer", "default": 5000}},
             "required": ["code"]}),
    Tool(name="wokwi_serial_read", description="Compile and simulate a sketch, returning only the serial output",
         inputSchema={"type": "object", "properties": {
             "code": {"type": "string"}, "board": {"type": "string"},
             "duration_ms": {"type": "integer", "default": 3000}},
             "required": ["code"]}),
    Tool(name="wokwi_get_diagram", description="Return a minimal diagram.json for the given board FQBN",
         inputSchema={"type": "object", "properties": {"board": {"type": "string"}},
                      "required": ["board"]}),
    Tool(name="authenticate", description="Log in to the nff diagnosis server",
         inputSchema={"type": "object", "properties": {
             "email": {"type": "string"}, "password": {"type": "string"}}}),
    Tool(name="auth_logout", description="Log out from the nff diagnosis server",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="auth_status", description="Return authentication status for the nff diagnosis server",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="repair", description="Send serial/crash output to the diagnosis server and return a structured diagnosis",
         inputSchema={"type": "object", "properties": {
             "serial_output": {"type": "string"}, "build_id": {"type": "string"},
             "board": {"type": "string"}},
             "required": ["serial_output"]}),
]

_DISPATCH = {
    "list_devices": list_devices,
    "flash": flash,
    "serial_read": serial_read,
    "serial_write": serial_write,
    "reset_device": reset_device,
    "get_device_info": get_device_info,
    "wokwi_flash": wokwi_flash,
    "wokwi_serial_read": wokwi_serial_read,
    "wokwi_get_diagram": wokwi_get_diagram,
    "authenticate": authenticate,
    "auth_logout": auth_logout,
    "auth_status": auth_status,
    "repair": repair,
}


@app.list_tools()
async def _list_tools() -> list[Tool]:
    return _TOOLS


@app.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = _DISPATCH.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"ERROR: unknown tool {name!r}")]
    result = await handler(**arguments)
    if isinstance(result, dict):
        text = json.dumps(result)
    else:
        text = str(result)
    return [TextContent(type="text", text=text)]


def _make_starlette_app() -> Starlette:
    session_manager = StreamableHTTPSessionManager(
        app=app,
        json_response=False,
        stateless=False,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    async def handle_mcp(scope, receive, send) -> None:
        await session_manager.handle_request(scope, receive, send)

    return Starlette(
        routes=[Mount("/mcp", app=handle_mcp)],
        lifespan=lifespan,
    )


async def run_server(host: str = "127.0.0.1", port: int = 3000) -> None:
    starlette_app = _make_starlette_app()
    config = uvicorn.Config(starlette_app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
