"""nff MCP server — streamable-HTTP transport using the Python mcp library."""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from collections.abc import AsyncIterator
from typing import Any, Optional
from urllib.parse import parse_qs

import uvicorn
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool
from starlette.types import ASGIApp, Receive, Scope, Send

import nff.tools.arduino_lib as arduino_lib
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
    fqbn = board or toolchain.configured_board()
    resolved_port = port or config.get_default_device().get("port") or ""
    if not fqbn or not resolved_port:
        raise ValueError("Missing board or port — pass them explicitly or run `nff init`")
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


def _resolve_fqbn(board: Optional[str]) -> str:
    fqbn = board or toolchain.configured_board()
    if not fqbn:
        raise ValueError("Missing board — pass board= or run `nff init`")
    return fqbn


async def compile(
    code: Optional[str] = None,
    sketch: Optional[str] = None,
    board: Optional[str] = None,
) -> dict:
    """Compile only — no port, no upload. Returns structured artifacts."""
    from pathlib import Path
    try:
        fqbn = _resolve_fqbn(board)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not code and not sketch:
        return {"ok": False,
                "error": "provide sketch= (path to .ino or folder) or code="}
    try:
        result = toolchain.compile_only(
            fqbn,
            code=code,
            source=Path(sketch) if sketch else None,
        )
    except toolchain.ToolchainError as exc:
        return {"ok": False, "fqbn": fqbn, "error": str(exc)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "fqbn": fqbn, "error": f"{type(exc).__name__}: {exc}"}
    return result.to_dict()


async def flash(
    code: Optional[str] = None,
    board: Optional[str] = None,
    port: Optional[str] = None,
    sketch: Optional[str] = None,
) -> str:
    from pathlib import Path
    if not code and not sketch:
        return "ERROR: provide sketch= (path to .ino or folder) or code="
    try:
        fqbn, resolved_port = _resolve_fqbn_and_port(board, port)
    except ValueError as exc:
        return f"ERROR: {exc}"
    result = toolchain.flash(
        code=code,
        fqbn=fqbn,
        port=resolved_port,
        source=Path(sketch) if sketch else None,
    )
    # Non-blocking: prepend a stale-lib warning so an agent never assumes a
    # local SDK edit shipped when it actually built the stale synced library.
    warn = arduino_lib.local_sdk_newer_than_synced()
    if warn:
        return f"warning: {warn}\n{result}"
    return result


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
    fqbn = board or toolchain.configured_board()
    if not fqbn:
        return {"serial_output": "", "compile_output": "ERROR: Missing board",
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
    fqbn = board or toolchain.configured_board()
    if not fqbn:
        return "ERROR: Missing board"
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
    server_url = cfg.get("server_url", "https://nanoforgeflow.com")
    if email and password:
        try:
            tokens = auth_tools.direct_login(server_url, email, password)
        except Exception as exc:
            return f"ERROR: {exc}"
    elif email is None and password is None:
        try:
            sock, port = auth_tools.bind_callback_server()
            callback_url = f"http://127.0.0.1:{port}/callback"
            frontend_url = cfg.get("frontend_url", "https://nanoforgeflow.com")
            login_url = f"{frontend_url}/login?cb={auth_tools.percent_encode(callback_url)}"
            _pending_browser_auth["sock"] = sock
            try:
                auth_tools.open_browser(login_url)
            except Exception:
                pass
            return (
                f"OK: browser opened — sign in at {login_url} "
                "then call complete_authentication to finish"
            )
        except Exception as exc:
            return f"ERROR: {exc}"
    else:
        return "ERROR: provide both email and password, or neither for browser login"
    try:
        config.set_diagnosis_tokens(tokens.access_token, tokens.refresh_token)
    except Exception as exc:
        return f"ERROR: could not save tokens: {exc}"
    return "OK: authenticated"


async def complete_authentication(timeout: int = 120) -> str:
    from nff.tools import auth as auth_tools
    sock = _pending_browser_auth.pop("sock", None)
    if sock is None:
        return "ERROR: no pending browser authentication — call authenticate first"
    _pending_browser_auth.clear()
    loop = asyncio.get_event_loop()
    try:
        tokens = await asyncio.wait_for(
            loop.run_in_executor(None, auth_tools.wait_for_callback, sock, timeout),
            timeout=timeout + 5,
        )
    except (asyncio.TimeoutError, TimeoutError):
        return "ERROR: authentication timed out — call authenticate to try again"
    except Exception as exc:
        return f"ERROR: {exc}"
    try:
        config.set_diagnosis_tokens(tokens.access_token, tokens.refresh_token)
    except Exception as exc:
        return f"ERROR: could not save tokens: {exc}"
    return "OK: authenticated"


async def auth_logout() -> str:
    import requests as _requests
    cfg = config.get_diagnosis_config()
    server_url = cfg.get("server_url", "https://nanoforgeflow.com")
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
        config.clear_mcp_tokens()
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


async def auth_clear() -> str:
    try:
        config.clear_diagnosis_tokens()
        config.clear_mcp_tokens()
    except Exception as exc:
        return f"ERROR: {exc}"
    return "OK: tokens cleared"


async def auth_reconnect(
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    import subprocess
    from nff.tools import auth as auth_tools

    cfg = config.get_diagnosis_config()
    server_url = cfg.get("server_url", "https://nanoforgeflow.com")

    if email and password:
        try:
            tokens = auth_tools.direct_login(server_url, email, password)
        except Exception as exc:
            return f"ERROR: {exc}"
    elif email is None and password is None:
        try:
            sock, port = auth_tools.bind_callback_server()
            callback_url = f"http://127.0.0.1:{port}/callback"
            frontend_url = cfg.get("frontend_url", "https://nanoforgeflow.com")
            login_url = f"{frontend_url}/login?cb={auth_tools.percent_encode(callback_url)}"
            _pending_browser_auth["sock"] = sock
            try:
                auth_tools.open_browser(login_url)
            except Exception:
                pass
            tokens = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, auth_tools.wait_for_callback, sock, 300
                ),
                timeout=305,
            )
            _pending_browser_auth.clear()
        except (asyncio.TimeoutError, TimeoutError) as exc:
            _pending_browser_auth.clear()
            return "ERROR: authentication timed out"
        except Exception as exc:
            _pending_browser_auth.clear()
            return f"ERROR: {exc}"
    else:
        return "ERROR: provide both email and password, or neither for browser login"

    try:
        config.set_diagnosis_tokens(tokens.access_token, tokens.refresh_token)
    except Exception as exc:
        return f"ERROR: could not save tokens: {exc}"

    try:
        result = subprocess.run(
            [
                "claude", "mcp", "add",
                "--scope", "user",
                "--transport", "http",
                "--url", "http://127.0.0.1:3010/mcp",
                "nff",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return (
                "OK: authenticated but MCP re-registration failed — run manually: "
                "claude mcp add --scope user --transport http "
                "--url http://127.0.0.1:3010/mcp nff"
            )
    except Exception as exc:
        return f"OK: authenticated but could not re-register MCP: {exc}"

    return "OK: reconnected — Claude Code will re-authorize via OAuth on next connect"


async def repair(
    serial_output: str,
    build_id: Optional[str] = None,
    board: Optional[str] = None,
) -> str:
    import requests as _requests
    from nff.tools import auth as auth_tools
    from nff.commands.repair import call_repair
    cfg = config.get_diagnosis_config()
    server_url = cfg.get("server_url", "https://nanoforgeflow.com")
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
    Tool(name="compile",
         description="Compile a sketch ONLY — no board or port needed. Use this to verify a "
                     "sketch builds. Pass sketch= (path to a .ino file or sketch folder, "
                     "preferred) or code=. board= defaults to the configured board. Returns "
                     "JSON: {ok, fqbn, elf, image, artifacts, errors, output}.",
         inputSchema={"type": "object", "properties": {
             "sketch": {"type": "string", "description": "Path to a .ino/.cpp file or sketch folder"},
             "code": {"type": "string", "description": "Raw sketch source (alternative to sketch=)"},
             "board": {"type": "string", "description": "arduino-cli FQBN or PlatformIO board id; defaults to configured board"}}}),
    Tool(name="flash",
         description="Compile AND upload a sketch to the connected board (needs a port). "
                     "To only check that a sketch builds, use `compile` instead. Pass "
                     "sketch= (path, preferred) or code=.",
         inputSchema={"type": "object", "properties": {
             "sketch": {"type": "string", "description": "Path to a .ino file or sketch folder"},
             "code": {"type": "string", "description": "Raw sketch source (alternative to sketch=)"},
             "board": {"type": "string"}, "port": {"type": "string"}}}),
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
    Tool(name="wokwi_get_diagram", description="Return a minimal diagram.json for the given board (FQBN or PlatformIO board id)",
         inputSchema={"type": "object", "properties": {"board": {"type": "string"}},
                      "required": ["board"]}),
    Tool(name="authenticate",
         description="Log in to the nff diagnosis server. Provide email+password for direct "
                     "login. Omit both to open the browser login page and get a URL — then "
                     "call complete_authentication once you have signed in.",
         inputSchema={"type": "object", "properties": {
             "email": {"type": "string"}, "password": {"type": "string"}}}),
    Tool(name="complete_authentication",
         description="Wait for a browser login started by authenticate() to complete and "
                     "save the tokens. Optional timeout in seconds (default 120).",
         inputSchema={"type": "object", "properties": {
             "timeout": {"type": "integer", "default": 120}}}),
    Tool(name="auth_logout", description="Log out from the nff diagnosis server",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="auth_status", description="Return authentication status for the nff diagnosis server",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="auth_clear",
         description="Force-clear stored auth tokens locally without calling the server. "
                     "Use when the server is unreachable or tokens are corrupted.",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="auth_reconnect",
         description="Re-authenticate with the diagnosis server and re-register the MCP "
                     "connection in Claude Code with the new Bearer token. Provide email+password "
                     "for direct login, or omit both for browser OAuth. "
                     "Restart Claude Code afterwards.",
         inputSchema={"type": "object", "properties": {
             "email": {"type": "string"},
             "password": {"type": "string"}}}),
    Tool(name="repair", description="Send serial/crash output to the diagnosis server and return a structured diagnosis",
         inputSchema={"type": "object", "properties": {
             "serial_output": {"type": "string"}, "build_id": {"type": "string"},
             "board": {"type": "string"}},
             "required": ["serial_output"]}),
]

_DISPATCH = {
    "list_devices": list_devices,
    "compile": compile,
    "flash": flash,
    "serial_read": serial_read,
    "serial_write": serial_write,
    "reset_device": reset_device,
    "get_device_info": get_device_info,
    "wokwi_flash": wokwi_flash,
    "wokwi_serial_read": wokwi_serial_read,
    "wokwi_get_diagram": wokwi_get_diagram,
    "authenticate": authenticate,
    "complete_authentication": complete_authentication,
    "auth_logout": auth_logout,
    "auth_status": auth_status,
    "auth_clear": auth_clear,
    "auth_reconnect": auth_reconnect,
    "repair": repair,
}

# In-memory OAuth handshake state. These dicts only hold a request mid-flight (the
# few seconds between /oauth/authorize and /oauth/token); a server restart loses
# them but NOT the session — the issued MCP token lives in ~/.nff/config.json, so
# Claude reconnects without a new login.
_oauth_sessions: dict[str, dict] = {}  # session_id → {redirect_uri, state}
_auth_codes: dict[str, str] = {}       # auth_code → mcp access token
_pending_browser_auth: dict = {}       # at most one pending browser-login session

# Lifetime advertised for the opaque MCP access token handed to Claude Code. The
# token itself is STABLE (see _get_or_create_mcp_session): a refresh returns the
# same value with a fresh window, so this only governs how often Claude refreshes
# silently, never a user-facing prompt. Decoupled from the upstream Supabase JWT's
# (short) expiry, which is what caused re-auth every ~15 min.
_MCP_TOKEN_TTL = 86400  # 24h


def _get_or_create_mcp_session() -> str:
    """Return the persistent opaque MCP access token, creating it once if absent.

    The token (and its refresh partner) is stored in ~/.nff/config.json and
    deliberately does NOT rotate: it is a stable local credential, so the MCP
    session survives Claude Code restarts, brand-new sessions, and nff-server
    restarts. The user logs in once and keeps using it; the only thing that
    invalidates it is an explicit deauth — auth_logout / auth_clear /
    `nff auth logout` — all of which call config.clear_mcp_tokens().
    """
    existing = config.get_mcp_tokens().get("access_token")
    if existing:
        return existing
    access = "nff_at_" + secrets.token_urlsafe(32)
    refresh = "nff_rt_" + secrets.token_urlsafe(32)
    config.set_mcp_tokens(access, refresh)
    return access


async def _read_body(receive: Receive) -> bytes:
    body = b""
    while True:
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body", False):
            break
    return body


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


class _NffASGI:
    """ASGI app: OAuth 2.1 proxy endpoints + Bearer-authenticated /mcp transport."""

    def __init__(self, session_manager: StreamableHTTPSessionManager,
                 host: str = "127.0.0.1", port: int = 3010) -> None:
        self._sm = session_manager
        self._base = f"http://{host}:{port}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._handle_lifespan(receive, send)
        elif scope["type"] == "http":
            path: str = scope.get("path", "")
            if path.startswith("/.well-known/") or path.startswith("/oauth/"):
                await self._handle_oauth_route(path, scope, receive, send)
            elif path == "/mcp" or path.startswith("/mcp/"):
                headers_dict = dict(scope.get("headers", []))
                auth = headers_dict.get(b"authorization", b"").decode()
                presented = auth[len("Bearer "):] if auth.startswith("Bearer ") else ""
                mcp_token = config.get_mcp_tokens().get("access_token")
                # Legacy: sessions authorized before opaque tokens existed still hold
                # the raw Supabase JWT. Accept it once so the live session isn't broken;
                # Claude re-authorizes on its next expiry and upgrades to an MCP token.
                legacy_token = config.get_diagnosis_config().get("access_token")
                if not presented or presented not in (mcp_token, legacy_token):
                    await self._send_401(send)
                    return
                await self._sm.handle_request(scope, receive, send)
            else:
                await self._send_404(send)

    async def _send_json(self, send: Send, status: int, data: dict,
                         extra_headers: list | None = None) -> None:
        body = json.dumps(data).encode()
        headers: list = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ]
        if extra_headers:
            headers.extend(extra_headers)
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def _send_html(self, send: Send, status: int, html: str) -> None:
        body = html.encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"text/html; charset=utf-8"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def _send_redirect(self, send: Send, location: str) -> None:
        await send({"type": "http.response.start", "status": 302,
                    "headers": [(b"location", location.encode())]})
        await send({"type": "http.response.body", "body": b""})

    async def _send_401(self, send: Send) -> None:
        rm = f'{self._base}/.well-known/oauth-protected-resource'.encode()
        await self._send_json(send, 401, {"error": "unauthorized"}, extra_headers=[
            (b"www-authenticate",
             b'Bearer realm="nff", resource_metadata="' + rm + b'"'),
        ])

    async def _send_404(self, send: Send) -> None:
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b"Not Found"})

    async def _handle_oauth_route(self, path: str, scope: Scope,
                                   receive: Receive, send: Send) -> None:
        method: str = scope.get("method", "GET")
        qs = scope.get("query_string", b"").decode()
        params = parse_qs(qs)

        def first(key: str) -> str | None:
            return params.get(key, [None])[0]

        if path == "/.well-known/oauth-protected-resource":
            await self._send_json(send, 200, {
                "resource": self._base,
                "authorization_servers": [self._base],
            })

        elif path == "/.well-known/oauth-authorization-server":
            await self._send_json(send, 200, {
                "issuer": self._base,
                "authorization_endpoint": f"{self._base}/oauth/authorize",
                "token_endpoint": f"{self._base}/oauth/token",
                "registration_endpoint": f"{self._base}/oauth/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
            })

        elif path == "/oauth/register" and method == "POST":
            await self._send_json(send, 201, {
                "client_id": "nff-mcp",
                "client_secret": "unused",
                "redirect_uris": [],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            })

        elif path == "/oauth/authorize":
            redirect_uri = first("redirect_uri")
            state = first("state") or ""
            code_challenge = first("code_challenge") or ""
            if not redirect_uri:
                await self._send_json(send, 400, {"error": "missing redirect_uri"})
                return
            # Fast path: a local credential already exists — no browser needed.
            # This is what makes login persist across sessions. Either a stable
            # MCP token from an earlier session, or diagnosis tokens from a prior
            # login, short-circuits straight to an auth code bound to the SAME
            # stable MCP token. Only an explicit deauth clears both and forces the
            # browser back open.
            cfg = config.get_diagnosis_config()
            has_credential = bool(
                config.get_mcp_tokens().get("access_token") or cfg.get("access_token")
            )
            if has_credential:
                auth_code = secrets.token_urlsafe(32)
                _auth_codes[auth_code] = _get_or_create_mcp_session()
                sep = "&" if "?" in redirect_uri else "?"
                await self._send_redirect(send, f"{redirect_uri}{sep}code={auth_code}&state={state}")
                return
            session_id = secrets.token_urlsafe(16)
            _oauth_sessions[session_id] = {
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
            }
            server_url = cfg.get("server_url", "https://nanoforgeflow.com")
            callback_url = f"{self._base}/oauth/callback/{session_id}"
            from nff.tools.auth import percent_encode
            frontend_url = cfg.get("frontend_url", "https://nanoforgeflow.com")
            login_url = f"{frontend_url}/login?cb={percent_encode(callback_url)}"
            await self._send_redirect(send, login_url)

        elif path.startswith("/oauth/callback/"):
            session_id = path[len("/oauth/callback/"):]
            session = _oauth_sessions.pop(session_id, None)
            access_token = first("access_token")
            refresh_token = first("refresh_token") or ""
            if not access_token:
                await self._send_json(send, 400, {"error": "missing access_token in callback"})
                return
            try:
                config.set_diagnosis_tokens(access_token, refresh_token)
            except Exception:
                pass
            if not session:
                # Session expired (server restarted mid-flow). Tokens are saved —
                # show a success page so the user knows to reconnect Claude Code.
                await self._send_html(send, 200,
                    "<h2>Authenticated!</h2>"
                    "<p>Tokens saved. Please reconnect the nff MCP server in Claude Code "
                    "(Settings &rsaquo; MCP &rsaquo; nff &rsaquo; Reconnect) to complete "
                    "the handshake.</p>"
                )
                return
            auth_code = secrets.token_urlsafe(32)
            _auth_codes[auth_code] = _get_or_create_mcp_session()
            sep = "&" if "?" in session["redirect_uri"] else "?"
            location = (
                f"{session['redirect_uri']}{sep}"
                f"code={auth_code}&state={session['state']}"
            )
            await self._send_redirect(send, location)

        elif path == "/oauth/token" and method == "POST":
            body = await _read_body(receive)
            token_params = parse_qs(body.decode())

            def tp(key: str) -> str | None:
                return token_params.get(key, [None])[0]

            grant_type = tp("grant_type")

            if grant_type == "refresh_token":
                presented = tp("refresh_token")
                stored = config.get_mcp_tokens().get("refresh_token")
                if not presented or not stored or presented != stored:
                    await self._send_json(send, 400, {"error": "invalid_grant"})
                    return
                # Stable: hand back the SAME persistent pair with a fresh window.
                # Not rotating means Claude's stored credential keeps matching
                # config across sessions, so the user never has to log in again
                # until an explicit deauth clears the tokens.
                access_token = _get_or_create_mcp_session()
                refresh_token = config.get_mcp_tokens().get("refresh_token") or ""
                await self._send_json(send, 200, {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "bearer",
                    "expires_in": _MCP_TOKEN_TTL,
                })
                return

            code = tp("code")
            if not code or code not in _auth_codes:
                await self._send_json(send, 400, {"error": "invalid_grant"})
                return
            access_token = _auth_codes.pop(code)
            refresh_token = config.get_mcp_tokens().get("refresh_token") or ""
            await self._send_json(send, 200, {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": _MCP_TOKEN_TTL,
            })

        else:
            await self._send_404(send)

    async def _handle_lifespan(self, receive: Receive, send: Send) -> None:
        async with self._sm.run():
            await receive()  # lifespan.startup
            await send({"type": "lifespan.startup.complete"})
            await receive()  # lifespan.shutdown
            await send({"type": "lifespan.shutdown.complete"})


def _make_starlette_app(host: str = "127.0.0.1", port: int = 3010) -> _NffASGI:
    session_manager = StreamableHTTPSessionManager(
        app=app,
        json_response=False,
        stateless=False,
    )
    return _NffASGI(session_manager, host=host, port=port)


async def run_server(host: str = "127.0.0.1", port: int = 3010) -> None:
    asgi_app = _make_starlette_app(host=host, port=port)
    config = uvicorn.Config(asgi_app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
