"""Serial port I/O — read, write, reset, stream."""

import time
from typing import Callable, Generator, Optional

import serial

from nff import config
from nff.tools.retry import is_transient


class SerialError(Exception):
    pass


# Bounded retry for transient serial faults (port still held, re-enumerating).
_SERIAL_RETRIES = 2
_SERIAL_BACKOFF = (0.3, 0.8)


def _with_serial_retry(
    op: Callable[[], str], sleep: Callable[[float], None] = time.sleep
) -> str:
    """Run a serial op (returning a success string), retrying transient
    SerialExceptions. Returns ``"ERROR: <msg>"`` on a non-transient fault or
    once retries are exhausted."""
    last = ""
    for i in range(_SERIAL_RETRIES + 1):
        try:
            return op()
        except serial.SerialException as exc:
            last = str(exc)
            if i == _SERIAL_RETRIES or not is_transient(last):
                return f"ERROR: {last}"
            sleep(_SERIAL_BACKOFF[min(i, len(_SERIAL_BACKOFF) - 1)])
    return f"ERROR: {last}"


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

    def _op() -> str:
        deadline = time.monotonic() + duration_ms / 1000.0
        buf = bytearray()
        sp = serial.Serial(p, b, timeout=0.1)
        try:
            while time.monotonic() < deadline:
                chunk = sp.read(sp.in_waiting or 1)
                if chunk:
                    buf.extend(chunk)
        finally:
            sp.close()
        return buf.decode("utf-8", errors="replace")

    return _with_serial_retry(_op)


def serial_write(data: str, port: Optional[str], baud: Optional[int]) -> str:
    try:
        p = _resolve_port(port)
    except SerialError as exc:
        return f"ERROR: {exc}"
    b = _resolve_baud(baud)
    if not data.endswith("\n"):
        data += "\n"
    raw = data.encode("utf-8")

    def _op() -> str:
        sp = serial.Serial(p, b, timeout=1)
        try:
            n = sp.write(raw)
        finally:
            sp.close()
        return f"OK: wrote {n} byte(s) to {p}"

    return _with_serial_retry(_op)


def reset_device(port: Optional[str]) -> str:
    try:
        p = _resolve_port(port)
    except SerialError as exc:
        return f"ERROR: {exc}"
    def _op() -> str:
        sp = serial.Serial(p, timeout=1)
        try:
            sp.dtr = False
            time.sleep(0.05)
            sp.dtr = True
            time.sleep(0.05)
        finally:
            sp.close()
        return f"OK: reset {p} via DTR toggle"

    return _with_serial_retry(_op)


def stream_lines(
    port: str, baud: int, timeout_s: Optional[float] = None
) -> Generator[str, None, None]:
    deadline = (time.monotonic() + timeout_s) if timeout_s is not None else None
    try:
        sp = serial.Serial(port, baud, timeout=0.1)
    except serial.SerialException as exc:
        # Port unavailable at open — yield a clean error line, no traceback.
        yield f"ERROR: {exc}"
        return
    try:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                break
            raw = sp.readline()
            if raw:
                yield raw.decode("utf-8", errors="replace").rstrip("\r\n")
    except serial.SerialException as exc:
        # Device unplugged mid-stream — surface it instead of crashing.
        yield f"ERROR: {exc}"
    finally:
        try:
            sp.close()
        except Exception:
            pass
