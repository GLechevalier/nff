"""Tests for nff.commands.doctor — individual check functions and CLI command."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from nff.commands.doctor import (
    Check,
    check_arduino_cli,
    check_claude_desktop,
    check_config,
    check_device,
    check_esptool,
    check_pyserial,
    check_python,
    doctor,
)


# ---------------------------------------------------------------------------
# check_python
# ---------------------------------------------------------------------------

def test_check_python_passes_on_current_interpreter():
    result = check_python()
    assert isinstance(result, Check)
    assert result.passed
    assert "Python" in result.detail


def test_check_python_fails_on_old_version(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(sys, "version_info", SimpleNamespace(major=3, minor=9, micro=0))
    result = check_python()
    assert not result.passed
    assert result.fix is not None


# ---------------------------------------------------------------------------
# check_arduino_cli
# ---------------------------------------------------------------------------

def test_check_arduino_cli_passes_when_found(monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli",
                        lambda: "/usr/bin/arduino-cli")
    monkeypatch.setattr("nff.tools.toolchain.arduino_cli_version",
                        lambda: "arduino-cli  Version: 1.4.1")
    result = check_arduino_cli()
    assert result.passed


def test_check_arduino_cli_fails_when_missing(monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.arduino_cli_version", lambda: None)
    result = check_arduino_cli()
    assert not result.passed
    assert result.fix is not None
    assert "arduino-cli" in result.fix.lower()


# ---------------------------------------------------------------------------
# check_esptool
# ---------------------------------------------------------------------------

def test_check_esptool_passes_when_found(monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.esptool_version", lambda: "esptool v5.1.0")
    monkeypatch.setattr("nff.tools.toolchain.find_esptool", lambda: "/usr/bin/esptool")
    result = check_esptool()
    assert result.passed


def test_check_esptool_fails_when_missing(monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.esptool_version", lambda: None)
    result = check_esptool()
    assert not result.passed
    assert result.fix is not None


# ---------------------------------------------------------------------------
# check_pyserial
# ---------------------------------------------------------------------------

def test_check_pyserial_passes():
    result = check_pyserial()
    assert result.passed
    assert "pyserial" in result.detail


# ---------------------------------------------------------------------------
# check_config
# ---------------------------------------------------------------------------

def test_check_config_fails_when_no_config(isolated_config, monkeypatch):
    from nff import config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", isolated_config / "config.json")
    result = check_config()
    assert not result.passed
    assert result.fix is not None


def test_check_config_passes_when_config_exists(isolated_config, monkeypatch):
    from nff import config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", isolated_config / "config.json")
    monkeypatch.setattr(cfg, "CONFIG_DIR", isolated_config)
    cfg.set_default_device(port="COM10", board="ESP32 (CP210x)",
                           fqbn="esp32:esp32:esp32", baud=115200)
    result = check_config()
    assert result.passed


def test_check_config_fails_on_bad_json(isolated_config, monkeypatch):
    from nff import config as cfg
    cfg_path = isolated_config / "config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("INVALID JSON {{{")
    monkeypatch.setattr(cfg, "CONFIG_PATH", cfg_path)
    result = check_config()
    assert not result.passed


# ---------------------------------------------------------------------------
# check_device
# ---------------------------------------------------------------------------

def test_check_device_fails_when_no_boards_detected(monkeypatch):
    monkeypatch.setattr("nff.tools.boards.serial.tools.list_ports.comports",
                        lambda: [])
    result = check_device()
    assert not result.passed
    assert result.fix is not None


def test_check_device_passes_when_board_detected_and_port_open(monkeypatch):
    from nff.tools.boards import DetectedDevice
    mock_device = DetectedDevice(port="COM10", board="ESP32 (CP210x)",
                                 fqbn="esp32:esp32:esp32",
                                 vendor_id="10c4", product_id="ea60")
    monkeypatch.setattr("nff.commands.doctor.boards_module.list_devices",
                        lambda: [mock_device])

    mock_conn = MagicMock()
    mock_conn.close = MagicMock()
    import serial as _serial
    monkeypatch.setattr(_serial, "Serial", lambda *a, **kw: mock_conn)

    result = check_device()
    assert result.passed
    assert "COM10" in result.detail


# ---------------------------------------------------------------------------
# check_claude_desktop
# ---------------------------------------------------------------------------

def test_check_claude_desktop_fails_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("nff.commands.doctor._CLAUDE_DESKTOP_CONFIG",
                        tmp_path / "nonexistent.json")
    result = check_claude_desktop()
    assert not result.passed


def test_check_claude_desktop_fails_when_nff_not_registered(tmp_path, monkeypatch):
    cfg_file = tmp_path / "claude_desktop_config.json"
    cfg_file.write_text(json.dumps({"mcpServers": {"other": {}}}))
    monkeypatch.setattr("nff.commands.doctor._CLAUDE_DESKTOP_CONFIG", cfg_file)
    result = check_claude_desktop()
    assert not result.passed


def test_check_claude_desktop_passes_when_nff_registered(tmp_path, monkeypatch):
    cfg_file = tmp_path / "claude_desktop_config.json"
    cfg_file.write_text(json.dumps({
        "mcpServers": {"nff": {"command": "nff", "args": ["mcp"]}}
    }))
    monkeypatch.setattr("nff.commands.doctor._CLAUDE_DESKTOP_CONFIG", cfg_file)
    result = check_claude_desktop()
    assert result.passed


def test_check_claude_desktop_fails_on_invalid_json(tmp_path, monkeypatch):
    cfg_file = tmp_path / "claude_desktop_config.json"
    cfg_file.write_text("NOT JSON {{{")
    monkeypatch.setattr("nff.commands.doctor._CLAUDE_DESKTOP_CONFIG", cfg_file)
    result = check_claude_desktop()
    assert not result.passed


# ---------------------------------------------------------------------------
# doctor CLI command
# ---------------------------------------------------------------------------

def test_doctor_exits_0_when_all_checks_pass(tmp_path, monkeypatch):
    from nff import config as cfg
    from nff.tools.boards import DetectedDevice

    mock_device = DetectedDevice(port="COM10", board="ESP32 (CP210x)",
                                 fqbn="esp32:esp32:esp32",
                                 vendor_id="10c4", product_id="ea60")
    monkeypatch.setattr("nff.commands.doctor.boards_module.list_devices",
                        lambda: [mock_device])
    monkeypatch.setattr("nff.tools.toolchain.arduino_cli_version",
                        lambda: "arduino-cli Version: 1.4.1")
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli",
                        lambda: "/usr/bin/arduino-cli")
    monkeypatch.setattr("nff.tools.toolchain.esptool_version",
                        lambda: "esptool v5.0")
    monkeypatch.setattr("nff.tools.toolchain.find_esptool",
                        lambda: "/usr/bin/esptool")

    cfg_file = tmp_path / "claude_desktop_config.json"
    cfg_file.write_text(json.dumps({
        "mcpServers": {"nff": {"command": "nff", "args": ["mcp"]}}
    }))
    monkeypatch.setattr("nff.commands.doctor._CLAUDE_DESKTOP_CONFIG", cfg_file)

    cfg_dir = tmp_path / ".nff"
    monkeypatch.setattr(cfg, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cfg, "CONFIG_PATH", cfg_dir / "config.json")
    cfg.set_default_device(port="COM10", board="ESP32 (CP210x)",
                           fqbn="esp32:esp32:esp32", baud=115200)

    import serial as _serial
    monkeypatch.setattr(_serial, "Serial", lambda *a, **kw: MagicMock())

    runner = CliRunner()
    result = runner.invoke(doctor, catch_exceptions=False)
    assert result.exit_code == 0, result.output


def test_doctor_exits_1_when_a_check_fails(monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.arduino_cli_version", lambda: None)
    runner = CliRunner()
    result = runner.invoke(doctor)
    assert result.exit_code == 1
