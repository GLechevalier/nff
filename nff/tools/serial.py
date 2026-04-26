"""pyserial read/write/capture helpers — physical hardware only.

All functions in this module communicate over a real USB/serial port.
For simulated hardware use nff.tools.wokwi (wokwi_flash / wokwi_serial_read).

  ┌──────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────┐
  │               Function               │                                    Purpose                                    │
  ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────┤
  │ serial_read(duration_ms, port, baud) │ Capture all incoming bytes for duration_ms ms, return as decoded string       │
  ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────┤
  │ serial_write(data, port, baud)       │ Send a string (appends \\n if absent), return byte-count confirmation         │
  ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────┤
  │ reset_device(port)                   │ Toggle DTR low→high to hardware-reset the board                               │
  ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────┤
  │ stream_lines(port, baud, timeout_s)  │ Generator yielding decoded lines as they arrive — for the interactive monitor │
  ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────┤
  │ open_connection(port, baud, timeout) │ Context manager returning a raw serial.Serial — reused by the functions above │
  └──────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import pathlib
import sys

# When this file is run directly (`python serial.py`), Python adds tools/ to
# sys.path, so `import serial` would import this file itself instead of pyserial.
# Detect that case and fix sys.path before pyserial or nff.config are imported.
if __name__ == "__main__":
    _here = pathlib.Path(__file__).resolve()
    _tools_dir = str(_here.parent)
    _pkg_parent = str(_here.parents[2])  # nff_cli_mcp/nff/ — parent of the nff package
    if _tools_dir in sys.path:
        sys.path.remove(_tools_dir)
    if _pkg_parent not in sys.path:
        sys.path.insert(0, _pkg_parent)

import time
from contextlib import contextmanager
from typing import Generator, Iterator

import serial

from nff.config import ConfigError, get_default_device


class SerialError(Exception):
    """Raised when a serial operation cannot be completed."""


def _resolve_port(port: str | None) -> str:
    if port is not None:
        return port
    try:
        cfg = get_default_device()
    except ConfigError as exc:
        raise SerialError(f"No port specified and config is unreadable: {exc}") from exc
    resolved = cfg.get("port")
    if not resolved:
        raise SerialError(
            "No port specified and no default port in config. "
            "Run `nff init` or pass --port explicitly."
        )
    return resolved


def _resolve_baud(baud: int | None) -> int:
    if baud is not None:
        return baud
    try:
        cfg = get_default_device()
        return int(cfg.get("baud") or 9600)
    except (ConfigError, ValueError):
        return 9600


@contextmanager
def open_connection(
    port: str | None = None,
    baud: int | None = None,
    timeout: float = 1.0,
) -> Generator[serial.Serial, None, None]:
    """Context manager that yields an open Serial connection.

    Args:
        port: Serial port path (e.g. ``COM3`` or ``/dev/ttyUSB0``).
            Falls back to the default device in config.
        baud: Baud rate. Falls back to config default (9600).
        timeout: Per-read timeout in seconds.

    Yields:
        An open :class:`serial.Serial` instance.

    Raises:
        SerialError: If the port cannot be resolved or opened.
    """
    resolved_port = _resolve_port(port)
    resolved_baud = _resolve_baud(baud)
    try:
        conn = serial.Serial(resolved_port, baudrate=resolved_baud, timeout=timeout)
    except serial.SerialException as exc:
        raise SerialError(f"Could not open {resolved_port}: {exc}") from exc
    try:
        yield conn
    finally:
        if conn.is_open:
            conn.close()


def serial_read(
    duration_ms: int = 3000,
    port: str | None = None,
    baud: int | None = None,
) -> str:
    """Capture serial output from a device for *duration_ms* milliseconds.

    Args:
        duration_ms: How long to listen, in milliseconds.
        port: Serial port. Falls back to config.
        baud: Baud rate. Falls back to config default (9600).

    Returns:
        Captured text decoded from the device.
        Returns ``"ERROR: <reason>"`` on failure so MCP callers can
        detect failure without exception handling.

    Note:
        Physical hardware only. For Wokwi simulation use
        ``nff.tools.wokwi.wokwi_serial_read`` (or the ``wokwi_serial_read``
        MCP tool).
    """
    try:
        deadline = time.monotonic() + duration_ms / 1000.0
        chunks: list[bytes] = []
        # Short per-read timeout so we can check the deadline on each iteration.
        with open_connection(port, baud, timeout=0.1) as conn:
            while time.monotonic() < deadline:
                chunk = conn.read(conn.in_waiting or 1)
                if chunk:
                    chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")
    except SerialError as exc:
        return f"ERROR: {exc}"
    except serial.SerialException as exc:
        return f"ERROR: {exc}"


def serial_write(
    data: str,
    port: str | None = None,
    baud: int | None = None,
) -> str:
    """Send *data* to the device over serial.

    A newline is appended to *data* if it does not already end with one,
    matching the convention Arduino's ``Serial.readStringUntil('\\n')`` expects.

    Args:
        data: String to transmit.
        port: Serial port. Falls back to config.
        baud: Baud rate. Falls back to config default (9600).

    Returns:
        ``"OK: wrote N byte(s) to <port>"`` on success,
        ``"ERROR: <reason>"`` on failure.
    """
    if not data.endswith("\n"):
        data = data + "\n"
    try:
        with open_connection(port, baud) as conn:
            written = conn.write(data.encode("utf-8"))
            return f"OK: wrote {written} byte(s) to {conn.port}"
    except SerialError as exc:
        return f"ERROR: {exc}"
    except serial.SerialException as exc:
        return f"ERROR: {exc}"


def reset_device(port: str | None = None) -> str:
    """Trigger a hardware reset by toggling the DTR line.

    Pulling DTR low then high causes most Arduino and ESP boards to reset,
    equivalent to pressing the physical reset button.

    Args:
        port: Serial port. Falls back to config.

    Returns:
        ``"OK: reset <port> via DTR toggle"`` on success,
        ``"ERROR: <reason>"`` on failure.
    """
    try:
        resolved_port = _resolve_port(port)
    except SerialError as exc:
        return f"ERROR: {exc}"

    try:
        conn = serial.Serial(resolved_port, timeout=1)
        conn.dtr = False
        time.sleep(0.05)
        conn.dtr = True
        time.sleep(0.05)
        conn.close()
    except serial.SerialException as exc:
        return f"ERROR: Could not reset {resolved_port}: {exc}"

    return f"OK: reset {resolved_port} via DTR toggle"


def stream_lines(
    port: str | None = None,
    baud: int | None = None,
    timeout_s: float | None = None,
) -> Iterator[str]:
    """Yield decoded lines from the device as they arrive.

    Intended for the interactive ``nff monitor`` command. The caller should
    catch :exc:`KeyboardInterrupt` to exit cleanly.

    Args:
        port: Serial port. Falls back to config.
        baud: Baud rate. Falls back to config default (9600).
        timeout_s: Stop after this many seconds. ``None`` means run forever.

    Yields:
        Lines decoded from the device (``\\r\\n`` stripped).

    Raises:
        SerialError: If the port cannot be opened or a read error occurs.

    Note:
        Physical hardware only. Wokwi simulation output is streamed directly
        by ``wokwi-cli`` — use ``nff wokwi run`` or the ``wokwi_flash`` MCP
        tool instead.
    """
    deadline = (time.monotonic() + timeout_s) if timeout_s is not None else None

    with open_connection(port, baud, timeout=1.0) as conn:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                break
            try:
                raw = conn.readline()
            except serial.SerialException as exc:
                raise SerialError(f"Read error on {conn.port}: {exc}") from exc
            if raw:
                yield raw.decode("utf-8", errors="replace").rstrip("\r\n")


if __name__ == "__main__":
    import sys

    print("=== nff serial self-test: reading 5 s from default device ===")
    output = serial_read(5000)
    if output.startswith("ERROR:"):
        print(output, file=sys.stderr)
        sys.exit(1)
    print(repr(output) if output else "(no data received in 5 s)")
