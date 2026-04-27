"""TDD contract for nff.tools.wokwi and the wokwi MCP tools.

Each test defines a behaviour the implementation must satisfy — nothing is
imported from a module that exists yet.  Run `pytest tests/test_wokwi.py` to
watch them all fail, then implement until they are all green.

Sections
--------
1.  generate_diagram     — minimal diagram.json dict per board
2.  _resolve_token       — env-var → config → None priority chain
3.  WokwiRunner.__init__ — token resolution at construction time
4.  WokwiRunner.run      — subprocess contract, result shape, error cases
5.  WokwiResult          — dataclass shape and .success property
6.  MCP wokwi_flash      — full compile → simulate → return dict flow
7.  MCP wokwi_serial_read — convenience wrapper returning serial text
8.  MCP wokwi_get_diagram — returns JSON string for Claude to extend
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from nff.tools.wokwi import (
    FQBN_TO_CHIP,
    WokwiError,
    WokwiResult,
    WokwiRunner,
    _resolve_token,
    generate_diagram,
)

import nff.tools.toolchain as toolchain

from nff.mcp_server import (
    wokwi_flash,
    wokwi_get_diagram,
    wokwi_serial_read,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completed_process(stdout: str = "", returncode: int = 0) -> MagicMock:
    """Minimal subprocess.CompletedProcess stand-in."""
    mock = MagicMock()
    mock.stdout = stdout
    mock.returncode = returncode
    return mock


def _make_wokwi_result(serial: str = "Hello!\n", exit_code: int = 0) -> WokwiResult:
    return WokwiResult(serial_output=serial, exit_code=exit_code)


# ---------------------------------------------------------------------------
# 1. generate_diagram
# ---------------------------------------------------------------------------

def test_generate_diagram_returns_a_dict():
    result = generate_diagram("arduino:avr:uno")
    assert isinstance(result, dict)


def test_generate_diagram_has_required_top_level_keys():
    diagram = generate_diagram("arduino:avr:uno")
    assert "version" in diagram
    assert "author" in diagram
    assert "editor" in diagram
    assert "parts" in diagram
    assert "connections" in diagram


def test_generate_diagram_version_is_one():
    diagram = generate_diagram("arduino:avr:uno")
    assert diagram["version"] == 1


def test_generate_diagram_parts_is_a_list():
    diagram = generate_diagram("arduino:avr:uno")
    assert isinstance(diagram["parts"], list)


def test_generate_diagram_connections_is_a_list():
    diagram = generate_diagram("arduino:avr:uno")
    assert isinstance(diagram["connections"], list)


def test_generate_diagram_parts_contains_exactly_one_entry():
    diagram = generate_diagram("arduino:avr:uno")
    assert len(diagram["parts"]) == 1


def test_generate_diagram_arduino_uno_chip():
    diagram = generate_diagram("arduino:avr:uno")
    assert diagram["parts"][0]["type"] == "wokwi-arduino-uno"


def test_generate_diagram_arduino_mega_chip():
    diagram = generate_diagram("arduino:avr:mega")
    assert diagram["parts"][0]["type"] == "wokwi-arduino-mega"


def test_generate_diagram_arduino_nano_chip():
    diagram = generate_diagram("arduino:avr:nano")
    assert diagram["parts"][0]["type"] == "wokwi-arduino-nano"


def test_generate_diagram_esp32_chip():
    diagram = generate_diagram("esp32:esp32:esp32")
    assert diagram["parts"][0]["type"] == "wokwi-esp32-devkit-v1"


def test_generate_diagram_esp8266_chip():
    diagram = generate_diagram("esp8266:esp8266:generic")
    assert diagram["parts"][0]["type"] == "wokwi-esp8266"


def test_generate_diagram_part_has_id_field():
    diagram = generate_diagram("arduino:avr:uno")
    part = diagram["parts"][0]
    assert "id" in part


def test_generate_diagram_unknown_fqbn_raises_wokwi_error():
    with pytest.raises(WokwiError, match="Unsupported"):
        generate_diagram("vendor:family:unknown_board")


# ---------------------------------------------------------------------------
# 2. FQBN_TO_CHIP map
# ---------------------------------------------------------------------------

def test_fqbn_to_chip_covers_arduino_uno():
    assert "arduino:avr:uno" in FQBN_TO_CHIP


def test_fqbn_to_chip_covers_esp32():
    assert "esp32:esp32:esp32" in FQBN_TO_CHIP


def test_fqbn_to_chip_values_are_strings():
    assert all(isinstance(v, str) for v in FQBN_TO_CHIP.values())


# ---------------------------------------------------------------------------
# 3. _resolve_token
# ---------------------------------------------------------------------------

def test_resolve_token_returns_env_var_when_set(monkeypatch, isolated_config):
    monkeypatch.setenv("WOKWI_CLI_TOKEN", "env-token-abc")
    assert _resolve_token() == "env-token-abc"


def test_resolve_token_ignores_config_when_env_var_set(monkeypatch, isolated_config):
    from nff import config as cfg
    cfg.set_wokwi_token("config-token-xyz")
    monkeypatch.setenv("WOKWI_CLI_TOKEN", "env-token-abc")
    assert _resolve_token() == "env-token-abc"


def test_resolve_token_falls_back_to_config(monkeypatch, isolated_config):
    monkeypatch.delenv("WOKWI_CLI_TOKEN", raising=False)
    from nff import config as cfg
    cfg.set_wokwi_token("config-token-xyz")
    assert _resolve_token() == "config-token-xyz"


def test_resolve_token_returns_none_when_neither_set(monkeypatch, isolated_config):
    monkeypatch.delenv("WOKWI_CLI_TOKEN", raising=False)
    assert _resolve_token() is None


# ---------------------------------------------------------------------------
# 4. WokwiRunner — construction
# ---------------------------------------------------------------------------

def test_wokwi_runner_stores_explicit_token():
    runner = WokwiRunner(token="explicit-tok")
    assert runner.token == "explicit-tok"


def test_wokwi_runner_resolves_token_from_env_when_not_explicit(monkeypatch, isolated_config):
    monkeypatch.setenv("WOKWI_CLI_TOKEN", "env-tok")
    runner = WokwiRunner()
    assert runner.token == "env-tok"


def test_wokwi_runner_token_is_none_when_nothing_configured(monkeypatch, isolated_config):
    monkeypatch.delenv("WOKWI_CLI_TOKEN", raising=False)
    runner = WokwiRunner()
    assert runner.token is None


def test_wokwi_runner_explicit_token_overrides_env(monkeypatch, isolated_config):
    monkeypatch.setenv("WOKWI_CLI_TOKEN", "env-tok")
    runner = WokwiRunner(token="explicit-tok")
    assert runner.token == "explicit-tok"


# ---------------------------------------------------------------------------
# 5. WokwiRunner.run — subprocess contract
# ---------------------------------------------------------------------------

def test_run_calls_wokwi_cli_run_subcommand(tmp_path):
    runner = WokwiRunner(token=None)
    with patch("subprocess.run", return_value=_make_completed_process()) as mock_proc:
        runner.run(project_dir=tmp_path, timeout_ms=5000)
    args = mock_proc.call_args[0][0]
    assert str(args[0]) == str(toolchain.find_wokwi_cli())
    assert args[1] == "run"


def test_run_passes_project_dir_as_positional_arg(tmp_path):
    runner = WokwiRunner(token=None)
    with patch("subprocess.run", return_value=_make_completed_process()) as mock_proc:
        runner.run(project_dir=tmp_path, timeout_ms=5000)
    args = mock_proc.call_args[0][0]
    assert str(tmp_path) in args


def test_run_passes_timeout_flag(tmp_path):
    runner = WokwiRunner(token=None)
    with patch("subprocess.run", return_value=_make_completed_process()) as mock_proc:
        runner.run(project_dir=tmp_path, timeout_ms=7000)
    args = mock_proc.call_args[0][0]
    assert "--timeout" in args
    assert "7000" in args


def test_run_sets_token_in_env_when_present(tmp_path):
    runner = WokwiRunner(token="my-secret-token")
    with patch("subprocess.run", return_value=_make_completed_process()) as mock_proc:
        runner.run(project_dir=tmp_path)
    kwargs = mock_proc.call_args[1]
    assert kwargs.get("env", {}).get("WOKWI_CLI_TOKEN") == "my-secret-token"


def test_run_does_not_set_token_env_when_none(tmp_path, monkeypatch):
    monkeypatch.delenv("WOKWI_CLI_TOKEN", raising=False)
    runner = WokwiRunner(token=None)
    with patch("subprocess.run", return_value=_make_completed_process()) as mock_proc:
        runner.run(project_dir=tmp_path)
    kwargs = mock_proc.call_args[1]
    env = kwargs.get("env", {})
    assert "WOKWI_CLI_TOKEN" not in env


def test_run_captures_stdout(tmp_path):
    runner = WokwiRunner(token=None)
    mock_proc = _make_completed_process(stdout="Counter: 1\nCounter: 2\n", returncode=0)
    with patch("subprocess.run", return_value=mock_proc):
        result = runner.run(project_dir=tmp_path)
    assert "Counter: 1" in result.serial_output


def test_run_returns_wokwi_result_instance(tmp_path):
    runner = WokwiRunner(token=None)
    with patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
        result = runner.run(project_dir=tmp_path)
    assert isinstance(result, WokwiResult)


def test_run_exit_code_zero_on_success(tmp_path):
    runner = WokwiRunner(token=None)
    with patch("subprocess.run", return_value=_make_completed_process(returncode=0)):
        result = runner.run(project_dir=tmp_path)
    assert result.exit_code == 0


def test_run_exit_code_nonzero_on_failure(tmp_path):
    runner = WokwiRunner(token=None)
    with patch("subprocess.run", return_value=_make_completed_process(returncode=1)):
        result = runner.run(project_dir=tmp_path)
    assert result.exit_code == 1


def test_run_raises_wokwi_error_when_cli_not_found(tmp_path):
    runner = WokwiRunner(token=None)
    with patch("subprocess.run", side_effect=FileNotFoundError("wokwi-cli not found")):
        with pytest.raises(WokwiError, match="wokwi-cli"):
            runner.run(project_dir=tmp_path)


def test_run_raises_wokwi_error_on_subprocess_timeout(tmp_path):
    runner = WokwiRunner(token=None)
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("wokwi-cli", 10)):
        with pytest.raises(WokwiError, match="timed out"):
            runner.run(project_dir=tmp_path)


# ---------------------------------------------------------------------------
# 6. WokwiResult — shape and .success
# ---------------------------------------------------------------------------

def test_wokwi_result_success_true_when_exit_code_zero():
    r = WokwiResult(serial_output="ok", exit_code=0)
    assert r.success is True


def test_wokwi_result_success_false_when_exit_code_nonzero():
    r = WokwiResult(serial_output="", exit_code=1)
    assert r.success is False


def test_wokwi_result_simulated_is_always_true():
    r = WokwiResult(serial_output="", exit_code=0)
    assert r.simulated is True


def test_wokwi_result_serial_output_is_string():
    r = WokwiResult(serial_output="hello", exit_code=0)
    assert isinstance(r.serial_output, str)


# ---------------------------------------------------------------------------
# 7. MCP wokwi_flash
# ---------------------------------------------------------------------------

def _patch_flash_deps(compile_output="Sketch compiled.\n", exit_code=0,
                      serial_output="Hello Wokwi!\n", fqbn="arduino:avr:uno"):
    """Return a context-manager stack that patches compile + WokwiRunner."""
    compile_result = (compile_output, Path("/tmp/nff_sketch/build/firmware.elf"))
    runner_mock = MagicMock()
    runner_mock.run.return_value = WokwiResult(
        serial_output=serial_output,
        exit_code=exit_code,
    )
    runner_cls_mock = MagicMock(return_value=runner_mock)
    return compile_result, runner_cls_mock


async def test_wokwi_flash_returns_dict(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result, runner_cls = _patch_flash_deps()
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        result = await wokwi_flash("void setup(){} void loop(){}")
    assert isinstance(result, dict)


async def test_wokwi_flash_result_has_required_keys(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result, runner_cls = _patch_flash_deps()
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        result = await wokwi_flash("void setup(){} void loop(){}")
    assert "serial_output" in result
    assert "compile_output" in result
    assert "exit_code" in result
    assert "simulated" in result


async def test_wokwi_flash_simulated_is_true(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result, runner_cls = _patch_flash_deps()
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        result = await wokwi_flash("void setup(){} void loop(){}")
    assert result["simulated"] is True


async def test_wokwi_flash_returns_serial_output(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result, runner_cls = _patch_flash_deps(serial_output="LED ON\nLED OFF\n")
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        result = await wokwi_flash("void setup(){} void loop(){}")
    assert "LED ON" in result["serial_output"]


async def test_wokwi_flash_returns_compile_output(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result, runner_cls = _patch_flash_deps(compile_output="Sketch uses 924 bytes.\n")
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        result = await wokwi_flash("void setup(){} void loop(){}")
    assert "924 bytes" in result["compile_output"]


async def test_wokwi_flash_uses_explicit_board():
    compile_result = ("OK\n", Path("/tmp/build/firmware.elf"))
    runner_mock = MagicMock()
    runner_mock.run.return_value = WokwiResult(serial_output="", exit_code=0)
    runner_cls = MagicMock(return_value=runner_mock)
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result) as mock_compile, \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        await wokwi_flash("void setup(){}", board="arduino:avr:uno")
    fqbn_used = mock_compile.call_args[0][1]
    assert fqbn_used == "arduino:avr:uno"


async def test_wokwi_flash_uses_config_fqbn_when_board_omitted(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result = ("OK\n", Path("/tmp/build/firmware.elf"))
    runner_mock = MagicMock()
    runner_mock.run.return_value = WokwiResult(serial_output="", exit_code=0)
    runner_cls = MagicMock(return_value=runner_mock)
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result) as mock_compile, \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        await wokwi_flash("void setup(){}")
    fqbn_used = mock_compile.call_args[0][1]
    assert fqbn_used == "arduino:avr:uno"


async def test_wokwi_flash_returns_error_when_fqbn_missing(isolated_config):
    result = await wokwi_flash("void setup(){}")
    assert isinstance(result, dict)
    assert result.get("exit_code", 0) != 0 or "error" in str(result).lower()


async def test_wokwi_flash_returns_error_when_compile_fails(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    with patch("nff.mcp_server.toolchain.compile",
               side_effect=Exception("compile error: undeclared identifier")):
        result = await wokwi_flash("void setup(){")
    assert result["exit_code"] != 0
    assert "compile" in result.get("compile_output", "").lower() \
        or "error" in str(result).lower()


async def test_wokwi_flash_returns_error_when_wokwi_cli_missing(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result = ("OK\n", Path("/tmp/build/firmware.elf"))
    runner_mock = MagicMock()
    runner_mock.run.side_effect = WokwiError("wokwi-cli not found")
    runner_cls = MagicMock(return_value=runner_mock)
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        result = await wokwi_flash("void setup(){} void loop(){}")
    assert result["exit_code"] != 0
    assert "wokwi" in str(result).lower()


async def test_wokwi_flash_passes_timeout_to_runner(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result = ("OK\n", Path("/tmp/build/firmware.elf"))
    runner_mock = MagicMock()
    runner_mock.run.return_value = WokwiResult(serial_output="", exit_code=0)
    runner_cls = MagicMock(return_value=runner_mock)
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        await wokwi_flash("void setup(){} void loop(){}", timeout_ms=9000)
    _, kwargs = runner_mock.run.call_args
    assert kwargs.get("timeout_ms") == 9000


# ---------------------------------------------------------------------------
# 8. MCP wokwi_serial_read
# ---------------------------------------------------------------------------

async def test_wokwi_serial_read_returns_string(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result = ("OK\n", Path("/tmp/build/firmware.elf"))
    runner_mock = MagicMock()
    runner_mock.run.return_value = WokwiResult(serial_output="Blink!\n", exit_code=0)
    runner_cls = MagicMock(return_value=runner_mock)
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        result = await wokwi_serial_read("void setup(){} void loop(){}")
    assert isinstance(result, str)


async def test_wokwi_serial_read_returns_serial_output_text(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result = ("OK\n", Path("/tmp/build/firmware.elf"))
    runner_mock = MagicMock()
    runner_mock.run.return_value = WokwiResult(serial_output="Blink!\n", exit_code=0)
    runner_cls = MagicMock(return_value=runner_mock)
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        result = await wokwi_serial_read("void setup(){} void loop(){}")
    assert "Blink!" in result


async def test_wokwi_serial_read_passes_duration_as_timeout(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result = ("OK\n", Path("/tmp/build/firmware.elf"))
    runner_mock = MagicMock()
    runner_mock.run.return_value = WokwiResult(serial_output="", exit_code=0)
    runner_cls = MagicMock(return_value=runner_mock)
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        await wokwi_serial_read("void setup(){} void loop(){}", duration_ms=4000)
    _, kwargs = runner_mock.run.call_args
    assert kwargs.get("timeout_ms") == 4000


async def test_wokwi_serial_read_returns_error_string_on_failure(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result = ("OK\n", Path("/tmp/build/firmware.elf"))
    runner_mock = MagicMock()
    runner_mock.run.side_effect = WokwiError("wokwi-cli not found")
    runner_cls = MagicMock(return_value=runner_mock)
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        result = await wokwi_serial_read("void setup(){} void loop(){}")
    assert result.startswith("ERROR:")


async def test_wokwi_serial_read_returns_empty_string_when_no_output(isolated_config):
    from nff import config as cfg
    cfg.set_default_device(port="COM10", board="Arduino Uno",
                           fqbn="arduino:avr:uno", baud=9600)
    compile_result = ("OK\n", Path("/tmp/build/firmware.elf"))
    runner_mock = MagicMock()
    runner_mock.run.return_value = WokwiResult(serial_output="", exit_code=0)
    runner_cls = MagicMock(return_value=runner_mock)
    with patch("nff.mcp_server.toolchain.compile", return_value=compile_result), \
         patch("nff.mcp_server.wokwi_module.WokwiRunner", runner_cls):
        result = await wokwi_serial_read("void setup(){} void loop(){}")
    assert result == ""


# ---------------------------------------------------------------------------
# 9. MCP wokwi_get_diagram
# ---------------------------------------------------------------------------

async def test_wokwi_get_diagram_returns_a_string():
    result = await wokwi_get_diagram("arduino:avr:uno")
    assert isinstance(result, str)


async def test_wokwi_get_diagram_is_valid_json():
    result = await wokwi_get_diagram("arduino:avr:uno")
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


async def test_wokwi_get_diagram_arduino_uno_chip():
    result = await wokwi_get_diagram("arduino:avr:uno")
    diagram = json.loads(result)
    assert diagram["parts"][0]["type"] == "wokwi-arduino-uno"


async def test_wokwi_get_diagram_esp32_chip():
    result = await wokwi_get_diagram("esp32:esp32:esp32")
    diagram = json.loads(result)
    assert diagram["parts"][0]["type"] == "wokwi-esp32-devkit-v1"


async def test_wokwi_get_diagram_returns_error_string_for_unknown_board():
    result = await wokwi_get_diagram("vendor:family:unknown")
    assert result.startswith("ERROR:")
