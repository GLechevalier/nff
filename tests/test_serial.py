"""Tests for nff.tools.serial — port/baud resolution, read/write/reset, stream_lines."""

import time
from itertools import chain, repeat
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from nff.tools.serial import (
    SerialError,
    _resolve_baud,
    _resolve_port,
    reset_device,
    serial_read,
    serial_write,
    stream_lines,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_serial_mock(read_data=b"", in_waiting=0):
    """Return a MagicMock that behaves like a serial.Serial instance."""
    mock = MagicMock()
    mock.is_open = True
    mock.port = "COM10"
    mock.in_waiting = in_waiting
    mock.read.return_value = read_data
    mock.write.return_value = len(read_data)
    return mock


# ---------------------------------------------------------------------------
# _resolve_port
# ---------------------------------------------------------------------------

def test_resolve_port_returns_explicit_port():
    assert _resolve_port("COM5") == "COM5"


def test_resolve_port_falls_back_to_config(isolated_config, monkeypatch):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="ESP32 (CP210x)",
                           fqbn="esp32:esp32:esp32", baud=115200)
    assert _resolve_port(None) == "COM10"


def test_resolve_port_raises_serial_error_when_nothing_set(isolated_config):
    with pytest.raises(SerialError, match="No port"):
        _resolve_port(None)


# ---------------------------------------------------------------------------
# _resolve_baud
# ---------------------------------------------------------------------------

def test_resolve_baud_returns_explicit_baud():
    assert _resolve_baud(115200) == 115200


def test_resolve_baud_falls_back_to_config(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="X", fqbn="x:x:x", baud=57600)
    assert _resolve_baud(None) == 57600


def test_resolve_baud_defaults_to_9600_when_no_config(isolated_config):
    assert _resolve_baud(None) == 9600


# ---------------------------------------------------------------------------
# serial_read
# ---------------------------------------------------------------------------

def test_serial_read_captures_data(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="X", fqbn="x:x:x", baud=115200)

    payload = b"LED ON\nLED OFF\n"
    mock_conn = _make_serial_mock()
    mock_conn.in_waiting = len(payload)
    mock_conn.read.side_effect = chain([payload], repeat(b""))

    with patch("serial.Serial", return_value=mock_conn):
        result = serial_read(duration_ms=50, port="COM10", baud=115200)

    assert "LED ON" in result


def test_serial_read_returns_error_on_serial_exception():
    import serial
    with patch("serial.Serial", side_effect=serial.SerialException("port busy")):
        result = serial_read(duration_ms=50, port="COM99", baud=9600)
    assert result.startswith("ERROR:")
    assert "port busy" in result


def test_serial_read_returns_empty_string_when_no_data(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="X", fqbn="x:x:x", baud=115200)

    mock_conn = _make_serial_mock(read_data=b"", in_waiting=0)
    mock_conn.read.return_value = b""

    with patch("serial.Serial", return_value=mock_conn):
        result = serial_read(duration_ms=50, port="COM10", baud=115200)

    assert result == ""


# ---------------------------------------------------------------------------
# serial_write
# ---------------------------------------------------------------------------

def test_serial_write_appends_newline_if_absent():
    mock_conn = _make_serial_mock()
    mock_conn.write.return_value = 5

    with patch("serial.Serial", return_value=mock_conn):
        serial_write("ping", port="COM10", baud=9600)

    written_bytes = mock_conn.write.call_args[0][0]
    assert written_bytes.endswith(b"\n")


def test_serial_write_does_not_double_newline():
    mock_conn = _make_serial_mock()
    mock_conn.write.return_value = 6

    with patch("serial.Serial", return_value=mock_conn):
        serial_write("ping\n", port="COM10", baud=9600)

    written_bytes = mock_conn.write.call_args[0][0]
    assert written_bytes == b"ping\n"


def test_serial_write_returns_ok_string():
    mock_conn = _make_serial_mock()
    mock_conn.write.return_value = 5
    mock_conn.port = "COM10"

    with patch("serial.Serial", return_value=mock_conn):
        result = serial_write("ping", port="COM10", baud=9600)

    assert result.startswith("OK:")
    assert "COM10" in result


def test_serial_write_returns_error_on_serial_exception():
    import serial
    with patch("serial.Serial", side_effect=serial.SerialException("no device")):
        result = serial_write("hello", port="COM99", baud=9600)
    assert result.startswith("ERROR:")


# ---------------------------------------------------------------------------
# reset_device
# ---------------------------------------------------------------------------

def test_reset_device_returns_ok(monkeypatch):
    import serial as _serial
    mock_conn = MagicMock()
    mock_conn.dtr = True

    monkeypatch.setattr(_serial, "Serial", lambda *a, **kw: mock_conn)
    result = reset_device("COM10")

    assert result.startswith("OK:")
    assert "COM10" in result
    assert "DTR" in result


def test_reset_device_returns_error_on_serial_exception(monkeypatch):
    import serial as _serial
    monkeypatch.setattr(
        _serial, "Serial",
        lambda *a, **kw: (_ for _ in ()).throw(
            _serial.SerialException("access denied")
        ),
    )
    result = reset_device("COM99")
    assert result.startswith("ERROR:")


def test_reset_device_returns_error_when_no_port(isolated_config):
    result = reset_device(None)
    assert result.startswith("ERROR:")
    assert "No port" in result


# ---------------------------------------------------------------------------
# stream_lines
# ---------------------------------------------------------------------------

def test_stream_lines_yields_decoded_lines():
    mock_conn = MagicMock()
    mock_conn.is_open = True
    lines_data = [b"hello\r\n", b"world\r\n"]
    mock_conn.readline.side_effect = chain(lines_data, repeat(b""))

    with patch("serial.Serial", return_value=mock_conn):
        collected = []
        for line in stream_lines("COM10", 115200, timeout_s=0.2):
            collected.append(line)
            if len(collected) >= 2:
                break

    assert "hello" in collected
    assert "world" in collected


def test_stream_lines_strips_crlf():
    mock_conn = MagicMock()
    mock_conn.is_open = True
    mock_conn.readline.side_effect = chain([b"LED ON\r\n"], repeat(b""))

    with patch("serial.Serial", return_value=mock_conn):
        for line in stream_lines("COM10", 115200, timeout_s=0.1):
            assert line == "LED ON"
            break


def test_stream_lines_stops_at_timeout():
    mock_conn = MagicMock()
    mock_conn.is_open = True
    mock_conn.readline.return_value = b""

    start = time.monotonic()
    with patch("serial.Serial", return_value=mock_conn):
        list(stream_lines("COM10", 115200, timeout_s=0.15))
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, "stream_lines did not respect timeout"
