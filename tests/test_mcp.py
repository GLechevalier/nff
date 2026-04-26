"""Tests for nff.mcp_server — resolver helpers and async MCP tool handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nff.mcp_server import (
    _resolve_fqbn_and_port,
    _resolve_port,
    flash,
    get_device_info,
    list_devices,
    reset_device,
    serial_read,
    serial_write,
)


# ---------------------------------------------------------------------------
# _resolve_fqbn_and_port
# ---------------------------------------------------------------------------

def test_resolve_fqbn_and_port_returns_explicit_args(isolated_config):
    fqbn, port = _resolve_fqbn_and_port("arduino:avr:uno", "COM3")
    assert fqbn == "arduino:avr:uno"
    assert port == "COM3"


def test_resolve_fqbn_and_port_falls_back_to_config(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="ESP32 (CP210x)",
                           fqbn="esp32:esp32:esp32", baud=115200)
    fqbn, port = _resolve_fqbn_and_port(None, None)
    assert fqbn == "esp32:esp32:esp32"
    assert port == "COM10"


def test_resolve_fqbn_and_port_explicit_overrides_config(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="ESP32 (CP210x)",
                           fqbn="esp32:esp32:esp32", baud=115200)
    fqbn, port = _resolve_fqbn_and_port("arduino:avr:uno", "COM3")
    assert fqbn == "arduino:avr:uno"
    assert port == "COM3"


def test_resolve_fqbn_and_port_raises_when_both_missing(isolated_config):
    with pytest.raises(ValueError, match="Missing"):
        _resolve_fqbn_and_port(None, None)


def test_resolve_fqbn_and_port_raises_when_port_missing(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port=None, board="X", fqbn="x:x:x")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Missing"):
        _resolve_fqbn_and_port("arduino:avr:uno", None)


# ---------------------------------------------------------------------------
# _resolve_port (mcp_server helper)
# ---------------------------------------------------------------------------

def test_mcp_resolve_port_returns_explicit():
    assert _resolve_port("COM5") == "COM5"


def test_mcp_resolve_port_falls_back_to_config(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="ESP32 (CP210x)",
                           fqbn="esp32:esp32:esp32", baud=115200)
    assert _resolve_port(None) == "COM10"


def test_mcp_resolve_port_raises_when_nothing_set(isolated_config):
    with pytest.raises(ValueError, match="No port"):
        _resolve_port(None)


# ---------------------------------------------------------------------------
# list_devices MCP tool
# ---------------------------------------------------------------------------

async def test_list_devices_returns_device_list():
    from nff.tools.boards import DetectedDevice
    mock_device = DetectedDevice(
        port="COM10", board="ESP32 (CP210x)",
        fqbn="esp32:esp32:esp32", vendor_id="10c4", product_id="ea60",
    )
    with patch("nff.mcp_server.boards_module.list_devices", return_value=[mock_device]):
        result = await list_devices()

    assert len(result["devices"]) == 1
    d = result["devices"][0]
    assert d["port"] == "COM10"
    assert d["board"] == "ESP32 (CP210x)"
    assert d["fqbn"] == "esp32:esp32:esp32"
    assert d["vendor_id"] == "10c4"
    assert d["product_id"] == "ea60"


async def test_list_devices_returns_empty_list():
    with patch("nff.mcp_server.boards_module.list_devices", return_value=[]):
        result = await list_devices()
    assert result["devices"] == []


# ---------------------------------------------------------------------------
# flash MCP tool
# ---------------------------------------------------------------------------

async def test_flash_returns_ok_on_success(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="ESP32 (CP210x)",
                           fqbn="esp32:esp32:esp32", baud=115200)
    with patch("nff.mcp_server.toolchain.flash", return_value="OK: flash complete"):
        result = await flash("void setup(){} void loop(){}")
    assert result == "OK: flash complete"


async def test_flash_returns_error_when_fqbn_missing(isolated_config):
    result = await flash("void setup(){}")
    assert result.startswith("ERROR:")


async def test_flash_passes_explicit_board_and_port():
    with patch("nff.mcp_server.toolchain.flash", return_value="OK: done") as mock_flash:
        await flash("void setup(){}", board="arduino:avr:uno", port="COM3")
    mock_flash.assert_called_once_with("void setup(){}", "arduino:avr:uno", "COM3")


# ---------------------------------------------------------------------------
# serial_read MCP tool
# ---------------------------------------------------------------------------

async def test_serial_read_returns_captured_text():
    with patch("nff.mcp_server.serial_module.serial_read", return_value="LED ON\nLED OFF\n"):
        result = await serial_read(duration_ms=500, port="COM10", baud=115200)
    assert "LED ON" in result


async def test_serial_read_passes_duration_port_baud():
    with patch("nff.mcp_server.serial_module.serial_read", return_value="") as mock_read:
        await serial_read(duration_ms=1000, port="COM10", baud=9600)
    mock_read.assert_called_once_with(1000, "COM10", 9600)


# ---------------------------------------------------------------------------
# serial_write MCP tool
# ---------------------------------------------------------------------------

async def test_serial_write_returns_ok():
    with patch("nff.mcp_server.serial_module.serial_write",
               return_value="OK: wrote 5 byte(s) to COM10"):
        result = await serial_write("ping", port="COM10", baud=9600)
    assert result.startswith("OK:")


async def test_serial_write_returns_error_on_failure():
    with patch("nff.mcp_server.serial_module.serial_write",
               return_value="ERROR: port busy"):
        result = await serial_write("ping", port="COM99", baud=9600)
    assert result.startswith("ERROR:")


# ---------------------------------------------------------------------------
# reset_device MCP tool
# ---------------------------------------------------------------------------

async def test_reset_device_returns_ok():
    with patch("nff.mcp_server.serial_module.reset_device",
               return_value="OK: reset COM10 via DTR toggle"):
        result = await reset_device(port="COM10")
    assert result.startswith("OK:")


async def test_reset_device_passes_port():
    with patch("nff.mcp_server.serial_module.reset_device",
               return_value="OK: reset COM10 via DTR toggle") as mock_reset:
        await reset_device(port="COM10")
    mock_reset.assert_called_once_with("COM10")


# ---------------------------------------------------------------------------
# get_device_info MCP tool
# ---------------------------------------------------------------------------

async def test_get_device_info_returns_full_info(isolated_config):
    from nff import config as cfg
    from nff.tools.boards import DetectedDevice
    cfg.set_default_device(port="COM10", board="ESP32 (CP210x)",
                           fqbn="esp32:esp32:esp32", baud=115200)
    mock_device = DetectedDevice(
        port="COM10", board="ESP32 (CP210x)",
        fqbn="esp32:esp32:esp32", vendor_id="10c4", product_id="ea60",
    )
    with patch("nff.mcp_server.boards_module.find_device", return_value=mock_device):
        result = await get_device_info(port="COM10")

    assert result["port"] == "COM10"
    assert result["board"] == "ESP32 (CP210x)"
    assert result["fqbn"] == "esp32:esp32:esp32"
    assert result["baud"] == 115200
    assert result["vendor_id"] == "10c4"


async def test_get_device_info_returns_error_when_no_port(isolated_config):
    result = await get_device_info(port=None)
    assert "error" in result


async def test_get_device_info_falls_back_to_config_when_board_unknown(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Custom Board",
                           fqbn="custom:x:x", baud=9600)
    with patch("nff.mcp_server.boards_module.find_device", return_value=None):
        result = await get_device_info(port="COM10")

    assert result["port"] == "COM10"
    assert result["board"] == "Custom Board"
