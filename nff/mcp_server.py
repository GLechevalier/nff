"""nff MCP server — exposes hardware tools to Claude Code via stdio."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from nff import config as cfg_module
from nff.tools import boards as boards_module
from nff.tools import serial as serial_module
from nff.tools import toolchain
from nff.tools import wokwi as wokwi_module

mcp = FastMCP("nff")


# ---------------------------------------------------------------------------
# Internal resolvers
# ---------------------------------------------------------------------------

def _resolve_fqbn_and_port(
    board: str | None,
    port: str | None,
) -> tuple[str, str]:
    """Return (fqbn, port) from args + config. Raises ValueError if either is missing."""
    try:
        device = cfg_module.get_default_device()
    except cfg_module.ConfigError:
        device = {}

    fqbn = board or device.get("fqbn") or ""
    resolved_port = port or device.get("port") or ""

    missing: list[str] = []
    if not fqbn:
        missing.append("board FQBN (pass board= or run `nff init`)")
    if not resolved_port:
        missing.append("port (pass port= or run `nff init`)")
    if missing:
        raise ValueError("Missing: " + ", ".join(missing))

    return fqbn, resolved_port


def _resolve_port(port: str | None) -> str:
    """Return port from arg or config. Raises ValueError if unresolvable."""
    if port:
        return port
    try:
        resolved = cfg_module.get_default_device().get("port") or ""
        if resolved:
            return resolved
    except cfg_module.ConfigError:
        pass
    raise ValueError("No port specified and no default port in config. Run `nff init`.")


def _resolve_fqbn(board: str | None) -> str:
    """Return FQBN from arg or config. Raises ValueError if unresolvable."""
    if board:
        return board
    try:
        fqbn = cfg_module.get_default_device().get("fqbn") or ""
        if fqbn:
            return fqbn
    except cfg_module.ConfigError:
        pass
    raise ValueError("Missing board FQBN (pass board= or run `nff init`)")


# ---------------------------------------------------------------------------
# Hardware tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_devices() -> dict[str, Any]:
    """List all connected USB/serial devices with board identification."""
    devices = await asyncio.to_thread(boards_module.list_devices)
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


@mcp.tool()
async def flash(
    code: str,
    board: str | None = None,
    port: str | None = None,
) -> str:
    """Compile and upload an Arduino/ESP sketch to the connected board.

    Args:
        code: Full Arduino/C++ sketch source code.
        board: Board FQBN, e.g. 'arduino:avr:uno'. Defaults to config.
        port: Serial port, e.g. '/dev/ttyUSB0'. Defaults to config.

    Returns:
        Starts with 'OK:' on success or 'ERROR:' on failure.
    """
    try:
        fqbn, resolved_port = _resolve_fqbn_and_port(board, port)
    except ValueError as exc:
        return f"ERROR: {exc}"

    return await asyncio.to_thread(toolchain.flash, code, fqbn, resolved_port)


@mcp.tool()
async def serial_read(
    duration_ms: int = 3000,
    port: str | None = None,
    baud: int | None = None,
) -> str:
    """Capture serial output from the device for a given duration.

    Args:
        duration_ms: How long to listen in milliseconds. Default 3000.
        port: Serial port. Defaults to config.
        baud: Baud rate. Defaults to config default (9600).

    Returns:
        Captured text from the device, or 'ERROR: <reason>' on failure.
    """
    return await asyncio.to_thread(serial_module.serial_read, duration_ms, port, baud)


@mcp.tool()
async def serial_write(
    data: str,
    port: str | None = None,
    baud: int | None = None,
) -> str:
    """Send a string to the device over serial.

    Args:
        data: String to transmit. A newline is appended if absent.
        port: Serial port. Defaults to config.
        baud: Baud rate. Defaults to config default (9600).

    Returns:
        'OK: wrote N byte(s) to <port>' on success, 'ERROR: <reason>' on failure.
    """
    return await asyncio.to_thread(serial_module.serial_write, data, port, baud)


@mcp.tool()
async def reset_device(port: str | None = None) -> str:
    """Trigger a hardware reset on the board by toggling the DTR line.

    Equivalent to pressing the physical reset button. Works on Arduino
    and most ESP32/ESP8266 boards.

    Args:
        port: Serial port. Defaults to config.

    Returns:
        'OK: reset <port> via DTR toggle' on success, 'ERROR: <reason>' on failure.
    """
    return await asyncio.to_thread(serial_module.reset_device, port)


@mcp.tool()
async def get_device_info(port: str | None = None) -> dict[str, Any]:
    """Return detailed information about the connected device.

    Args:
        port: Serial port to query. Defaults to the config default device.

    Returns:
        Dict with port, board, fqbn, baud, vendor_id, product_id, wokwi_chip.
        Contains 'error' key on failure.
    """
    try:
        resolved_port = _resolve_port(port)
    except ValueError as exc:
        return {"error": str(exc)}

    device = await asyncio.to_thread(boards_module.find_device, resolved_port)

    try:
        cfg = cfg_module.get_default_device()
    except cfg_module.ConfigError:
        cfg = {}

    baud = int(cfg.get("baud") or 9600)

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

    # Port is known but board isn't in BOARD_MAP — return what config has.
    return {
        "port": resolved_port,
        "board": cfg.get("board") or "Unknown",
        "fqbn": cfg.get("fqbn") or "",
        "baud": baud,
        "vendor_id": "",
        "product_id": "",
        "wokwi_chip": None,
    }


# ---------------------------------------------------------------------------
# Wokwi simulation tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def wokwi_flash(
    code: str,
    board: str | None = None,
    timeout_ms: int = 5000,
) -> dict[str, Any]:
    """Compile a sketch and run it in the Wokwi simulator — no hardware needed.

    Compiles *code* with arduino-cli (no upload), generates a minimal
    diagram.json for the target board, then runs wokwi-cli to simulate.

    Args:
        code: Full Arduino/C++ sketch source code.
        board: Board FQBN, e.g. 'arduino:avr:uno'. Defaults to config.
        timeout_ms: Simulation wall-clock timeout in milliseconds. Default 5000.

    Returns:
        Dict with keys: serial_output, compile_output, exit_code, simulated.
        exit_code is non-zero on any failure; check compile_output for details.
    """
    try:
        fqbn = _resolve_fqbn(board)
    except ValueError as exc:
        return {
            "serial_output": "",
            "compile_output": str(exc),
            "exit_code": 1,
            "simulated": True,
        }

    try:
        compile_output, elf_path = await asyncio.to_thread(
            toolchain.compile, code, fqbn
        )
    except Exception as exc:
        return {
            "serial_output": "",
            "compile_output": f"compile error: {exc}",
            "exit_code": 1,
            "simulated": True,
        }

    with tempfile.TemporaryDirectory() as _tmpdir:
        project_dir = Path(_tmpdir)
        try:
            diagram = wokwi_module.generate_diagram(fqbn)
            (project_dir / "diagram.json").write_text(
                json.dumps(diagram, indent=2), encoding="utf-8"
            )
            wokwi_module.write_wokwi_toml(project_dir, elf_path)
        except wokwi_module.WokwiError as exc:
            return {
                "serial_output": "",
                "compile_output": f"{compile_output}\nwokwi setup error: {exc}",
                "exit_code": 1,
                "simulated": True,
            }

        try:
            runner = wokwi_module.WokwiRunner()
            sim_result = await asyncio.to_thread(
                runner.run, project_dir, timeout_ms=timeout_ms
            )
        except wokwi_module.WokwiError as exc:
            return {
                "serial_output": f"wokwi error: {exc}",
                "compile_output": compile_output,
                "exit_code": 1,
                "simulated": True,
            }

    return {
        "serial_output": sim_result.serial_output,
        "compile_output": compile_output,
        "exit_code": sim_result.exit_code,
        "simulated": True,
    }


@mcp.tool()
async def wokwi_serial_read(
    code: str,
    board: str | None = None,
    duration_ms: int = 3000,
) -> str:
    """Compile and simulate a sketch, returning only the serial output.

    Convenience wrapper around wokwi_flash for when only serial output
    matters and compile details are not needed.

    Args:
        code: Full Arduino/C++ sketch source code.
        board: Board FQBN. Defaults to config.
        duration_ms: Simulation duration in milliseconds. Default 3000.

    Returns:
        Captured serial output as a plain string, or 'ERROR: <reason>'
        on failure.
    """
    try:
        fqbn = _resolve_fqbn(board)
    except ValueError as exc:
        return f"ERROR: {exc}"

    try:
        compile_output, elf_path = await asyncio.to_thread(
            toolchain.compile, code, fqbn
        )
    except Exception as exc:
        return f"ERROR: compile failed: {exc}"

    with tempfile.TemporaryDirectory() as _tmpdir:
        project_dir = Path(_tmpdir)
        try:
            diagram = wokwi_module.generate_diagram(fqbn)
            (project_dir / "diagram.json").write_text(
                json.dumps(diagram, indent=2), encoding="utf-8"
            )
            wokwi_module.write_wokwi_toml(project_dir, elf_path)
        except wokwi_module.WokwiError as exc:
            return f"ERROR: {exc}"

        try:
            runner = wokwi_module.WokwiRunner()
            sim_result = await asyncio.to_thread(
                runner.run, project_dir, timeout_ms=duration_ms
            )
        except wokwi_module.WokwiError as exc:
            return f"ERROR: {exc}"

    return sim_result.serial_output


@mcp.tool()
async def wokwi_get_diagram(board: str) -> str:
    """Return a minimal Wokwi diagram.json as a JSON string for the given board.

    The diagram contains a single MCU component with no wiring. Claude can
    extend it by parsing the JSON, adding parts and connections, then
    writing the result back to diagram.json before calling wokwi_flash.

    Args:
        board: Board FQBN, e.g. 'arduino:avr:uno'.

    Returns:
        A JSON string (pretty-printed) ready to write to diagram.json,
        or 'ERROR: <reason>' if the board is not supported by Wokwi.
    """
    try:
        diagram = wokwi_module.generate_diagram(board)
    except wokwi_module.WokwiError as exc:
        return f"ERROR: {exc}"
    return json.dumps(diagram, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the MCP server on stdio. Invoked by `nff mcp`."""
    mcp.run()


if __name__ == "__main__":
    main()
