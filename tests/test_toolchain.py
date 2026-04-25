"""Tests for nff.tools.toolchain — sketch writing, RunResult, subproc wrappers, flash."""

import sys
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from nff.tools.toolchain import (
    ProcessStream,
    RunResult,
    ToolchainError,
    _require_arduino_cli,
    _run,
    esptool_flash,
    find_arduino_cli,
    find_esptool,
    flash,
    write_sketch,
)


# ---------------------------------------------------------------------------
# write_sketch
# ---------------------------------------------------------------------------

def test_write_sketch_creates_ino_in_default_dir(tmp_path, monkeypatch):
    import nff.tools.toolchain as tc
    monkeypatch.setattr(tc, "_SKETCH_DIR", tmp_path / "nff_sketch")
    code = "void setup(){} void loop(){}"
    result = write_sketch(code)
    ino = result / "nff_sketch.ino"
    assert ino.exists()
    assert ino.read_text() == code


def test_write_sketch_uses_custom_dir(tmp_path):
    custom = tmp_path / "my_sketch"
    result = write_sketch("void setup(){}", sketch_dir=custom)
    assert result == custom
    assert (custom / "my_sketch.ino").exists()


def test_write_sketch_overwrites_existing(tmp_path):
    sketch_dir = tmp_path / "s"
    write_sketch("v1", sketch_dir=sketch_dir)
    write_sketch("v2", sketch_dir=sketch_dir)
    assert (sketch_dir / "s.ino").read_text() == "v2"


# ---------------------------------------------------------------------------
# RunResult.output
# ---------------------------------------------------------------------------

def test_run_result_output_combines_stdout_and_stderr():
    r = RunResult(success=True, stdout="compiled ok\n", stderr="warning: foo\n", returncode=0)
    assert "compiled ok" in r.output
    assert "warning: foo" in r.output


def test_run_result_output_strips_whitespace():
    r = RunResult(success=True, stdout="  ok  ", stderr="  ", returncode=0)
    assert r.output == "ok"


def test_run_result_output_empty_when_both_blank():
    r = RunResult(success=True, stdout="", stderr="", returncode=0)
    assert r.output == ""


def test_run_result_output_only_stderr():
    r = RunResult(success=False, stdout="", stderr="error: undefined", returncode=1)
    assert r.output == "error: undefined"


# ---------------------------------------------------------------------------
# _run — uses real Python subprocess, no mocking needed
# ---------------------------------------------------------------------------

def test_run_success():
    result = _run([sys.executable, "-c", "print('hello')"])
    assert result.success
    assert result.returncode == 0
    assert "hello" in result.stdout


def test_run_nonzero_exit():
    result = _run([sys.executable, "-c", "import sys; sys.exit(42)"])
    assert not result.success
    assert result.returncode == 42


def test_run_captures_stderr():
    result = _run([sys.executable, "-c",
                   "import sys; sys.stderr.write('err msg\\n')"])
    assert "err msg" in result.stderr


def test_run_raises_toolchain_error_on_missing_exe():
    with pytest.raises(ToolchainError, match="Executable not found"):
        _run(["nonexistent_binary_xyz_abc_123"])


def test_run_raises_toolchain_error_on_timeout():
    with pytest.raises(ToolchainError, match="timed out"):
        _run([sys.executable, "-c", "import time; time.sleep(10)"], timeout=1)


# ---------------------------------------------------------------------------
# ProcessStream
# ---------------------------------------------------------------------------

def test_process_stream_yields_lines_and_sets_returncode(tmp_path):
    script = tmp_path / "script.py"
    script.write_text("print('line1')\nprint('line2')\n")
    stream = ProcessStream([sys.executable, str(script)])
    lines = list(stream)
    assert "line1" in lines
    assert "line2" in lines
    assert stream.returncode == 0


def test_process_stream_nonzero_returncode(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("import sys; sys.exit(3)")
    stream = ProcessStream([sys.executable, str(script)])
    list(stream)
    assert stream.returncode == 3


def test_process_stream_raises_on_missing_exe():
    stream = ProcessStream(["nonexistent_binary_xyz_abc_123"])
    with pytest.raises(ToolchainError, match="Executable not found"):
        list(stream)


def test_process_stream_returncode_is_none_before_iteration():
    stream = ProcessStream([sys.executable, "-c", "pass"])
    assert stream.returncode is None


# ---------------------------------------------------------------------------
# find_arduino_cli / find_esptool
# ---------------------------------------------------------------------------

def test_find_arduino_cli_returns_path_when_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/arduino-cli"
                        if name == "arduino-cli" else None)
    assert find_arduino_cli() == "/usr/bin/arduino-cli"


def test_find_arduino_cli_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert find_arduino_cli() is None


def test_find_esptool_prefers_esptool_py(monkeypatch):
    monkeypatch.setattr("shutil.which",
                        lambda name: "/usr/bin/esptool.py" if name == "esptool.py" else None)
    assert find_esptool() == "/usr/bin/esptool.py"


def test_find_esptool_falls_back_to_esptool(monkeypatch):
    monkeypatch.setattr("shutil.which",
                        lambda name: "/usr/bin/esptool" if name == "esptool" else None)
    assert find_esptool() == "/usr/bin/esptool"


# ---------------------------------------------------------------------------
# _require_arduino_cli
# ---------------------------------------------------------------------------

def test_require_arduino_cli_raises_when_missing(monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli", lambda: None)
    with pytest.raises(ToolchainError, match="arduino-cli not found"):
        _require_arduino_cli()


def test_require_arduino_cli_returns_path_when_found(monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli",
                        lambda: "/usr/bin/arduino-cli")
    assert _require_arduino_cli() == "/usr/bin/arduino-cli"


# ---------------------------------------------------------------------------
# flash() — combined write + compile + upload
# ---------------------------------------------------------------------------

def _ok_result(**kwargs):
    defaults = dict(success=True, stdout="compiled", stderr="", returncode=0)
    defaults.update(kwargs)
    return RunResult(**defaults)


def _fail_result(**kwargs):
    defaults = dict(success=False, stdout="", stderr="error msg", returncode=1)
    defaults.update(kwargs)
    return RunResult(**defaults)


def test_flash_returns_error_on_oserror_writing_sketch(tmp_path, monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.write_sketch",
                        MagicMock(side_effect=OSError("disk full")))
    result = flash("void setup(){}", "arduino:avr:uno", "COM3", sketch_dir=tmp_path)
    assert result.startswith("ERROR:")
    assert "disk full" in result


def test_flash_returns_error_when_arduino_cli_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli", lambda: None)
    result = flash("void setup(){}", "arduino:avr:uno", "COM3", sketch_dir=tmp_path)
    assert result.startswith("ERROR:")
    assert "arduino-cli" in result.lower()


def test_flash_returns_error_on_compile_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli",
                        lambda: "/fake/arduino-cli")
    monkeypatch.setattr("nff.tools.toolchain.compile_sketch",
                        lambda *a: _fail_result(stderr="undefined reference"))
    result = flash("void setup(){}", "arduino:avr:uno", "COM3", sketch_dir=tmp_path)
    assert result.startswith("ERROR:")
    assert "Compile failed" in result


def test_flash_returns_error_on_upload_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli",
                        lambda: "/fake/arduino-cli")
    monkeypatch.setattr("nff.tools.toolchain.compile_sketch",
                        lambda *a: _ok_result())
    monkeypatch.setattr("nff.tools.toolchain.upload_sketch",
                        lambda *a: _fail_result(stderr="wrong boot mode"))
    result = flash("void setup(){}", "esp32:esp32:esp32", "COM10", sketch_dir=tmp_path)
    assert result.startswith("ERROR:")
    assert "Upload failed" in result


def test_flash_returns_ok_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli",
                        lambda: "/fake/arduino-cli")
    monkeypatch.setattr("nff.tools.toolchain.compile_sketch",
                        lambda *a: _ok_result(stdout="Sketch uses 1234 bytes"))
    monkeypatch.setattr("nff.tools.toolchain.upload_sketch",
                        lambda *a: _ok_result(stdout="Hash of data verified"))
    result = flash("void setup(){}", "esp32:esp32:esp32", "COM10", sketch_dir=tmp_path)
    assert result.startswith("OK:")
    assert "flash complete" in result


def test_flash_includes_compile_output_in_ok_result(tmp_path, monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli",
                        lambda: "/fake/arduino-cli")
    monkeypatch.setattr("nff.tools.toolchain.compile_sketch",
                        lambda *a: _ok_result(stdout="Sketch uses 42 bytes"))
    monkeypatch.setattr("nff.tools.toolchain.upload_sketch",
                        lambda *a: _ok_result(stdout=""))
    result = flash("void setup(){}", "arduino:avr:uno", "COM3", sketch_dir=tmp_path)
    assert "42 bytes" in result


# ---------------------------------------------------------------------------
# esptool_flash
# ---------------------------------------------------------------------------

def test_esptool_flash_returns_ok_on_success(tmp_path, monkeypatch):
    bin_path = tmp_path / "firmware.bin"
    bin_path.write_bytes(b"\x00" * 16)

    monkeypatch.setattr("nff.tools.toolchain.find_esptool", lambda: "/fake/esptool")
    monkeypatch.setattr(
        "nff.tools.toolchain._run",
        lambda *a, **kw: RunResult(success=True, stdout="Hash verified", stderr="", returncode=0),
    )
    result = esptool_flash("COM10", bin_path)
    assert result.startswith("OK:")


def test_esptool_flash_returns_error_on_failure(tmp_path, monkeypatch):
    bin_path = tmp_path / "firmware.bin"
    bin_path.write_bytes(b"\x00")

    monkeypatch.setattr("nff.tools.toolchain.find_esptool", lambda: "/fake/esptool")
    monkeypatch.setattr(
        "nff.tools.toolchain._run",
        lambda *a, **kw: RunResult(success=False, stdout="", stderr="Wrong boot mode", returncode=2),
    )
    result = esptool_flash("COM10", bin_path)
    assert result.startswith("ERROR:")
    assert "Wrong boot mode" in result
