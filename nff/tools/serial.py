"""Serial port I/O — read, write, reset, stream."""

import time
from typing import Generator, Optional

import serial

from nff import config


class SerialError(Exception):
    pass


def _resolve_port(port: Optional[str]) -> str:
    if port:
        return port
    device = config.get_default_device()
    p = device.get("port")
    if p:
        return p
    raise SerialError("No port configured — pass port= or run `nff init`")


def _resolve_baud(baud: Optional[int]) -> int:
    if baud is not None:
        return baud
    device = config.get_default_device()
    return device.get("baud") or 9600


def serial_read(duration_ms: int, port: Optional[str], baud: Optional[int]) -> str:
    try:
        p = _resolve_port(port)
    except SerialError as exc:
        return f"ERROR: {exc}"
    b = _resolve_baud(baud)
    deadline = time.monotonic() + duration_ms / 1000.0
    buf = bytearray()
    try:
        sp = serial.Serial(p, b, timeout=0.1)
        try:
            while time.monotonic() < deadline:
                chunk = sp.read(sp.in_waiting or 1)
                if chunk:
                    buf.extend(chunk)
        finally:
            sp.close()
    except serial.SerialException as exc:
        return f"ERROR: {exc}"
    return buf.decode("utf-8", errors="replace")


def serial_write(data: str, port: Optional[str], baud: Optional[int]) -> str:
    try:
        p = _resolve_port(port)
    except SerialError as exc:
        return f"ERROR: {exc}"
    b = _resolve_baud(baud)
    if not data.endswith("\n"):
        data += "\n"
    raw = data.encode("utf-8")
    try:
        sp = serial.Serial(p, b, timeout=1)
        try:
            n = sp.write(raw)
        finally:
            sp.close()
    except serial.SerialException as exc:
        return f"ERROR: {exc}"
    return f"OK: wrote {n} byte(s) to {p}"


def reset_device(port: Optional[str]) -> str:
    try:
        p = _resolve_port(port)
    except SerialError as exc:
        return f"ERROR: {exc}"
    try:
        sp = serial.Serial(p, timeout=1)
        try:
            sp.dtr = False
            time.sleep(0.05)
            sp.dtr = True
            time.sleep(0.05)
        finally:
            sp.close()
    except serial.SerialException as exc:
        return f"ERROR: {exc}"
    return f"OK: reset {p} via DTR toggle"


def stream_lines(
    port: str, baud: int, timeout_s: Optional[float] = None
) -> Generator[str, None, None]:
    deadline = (time.monotonic() + timeout_s) if timeout_s is not None else None
    sp = serial.Serial(port, baud, timeout=0.1)
    try:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                break
            raw = sp.readline()
            if raw:
                yield raw.decode("utf-8", errors="replace").rstrip("\r\n")
    finally:
        sp.close()
