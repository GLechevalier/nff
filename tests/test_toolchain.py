"""Tests for nff.tools.toolchain — sketch writing, RunResult, subproc wrappers, flash."""

import sys
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from nff.tools.toolchain import (
    CompileResult,
    ProcessStream,
    RunResult,
    ToolchainError,
    _require_arduino_cli,
    _run,
    compile_only,
    discover_artifacts,
    elf_path_for,
    esptool_flash,
    find_arduino_cli,
    find_esptool,
    flash,
    resolve_sketch_dir,
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


def test_run_returns_failed_result_on_timeout():
    # A timeout is transient; _run reports it as a failed RunResult (rc=124) so
    # the retry layer can classify and retry it, rather than raising.
    result = _run([sys.executable, "-c", "import time; time.sleep(10)"], timeout=1)
    assert not result.success
    assert result.returncode == 124
    assert "timed out" in result.output


def test_compile_sketch_forwards_compile_timeout(tmp_path, monkeypatch):
    import nff.tools.toolchain as tc
    monkeypatch.setattr(tc, "find_arduino_cli", lambda: "/fake/cli")
    captured = {}

    def fake_run(cmd, timeout=tc._RUN_TIMEOUT):
        captured["timeout"] = timeout
        return RunResult(success=True, stdout="", stderr="", returncode=0)

    monkeypatch.setattr(tc, "_run", fake_run)
    tc.compile_sketch(tmp_path, "esp32:esp32:esp32")
    assert captured["timeout"] == tc._COMPILE_TIMEOUT


def test_compile_sketch_retries_transient_then_succeeds(tmp_path, monkeypatch):
    import nff.tools.toolchain as tc
    monkeypatch.setattr(tc, "find_arduino_cli", lambda: "/fake/cli")
    monkeypatch.setattr(tc._retry.time, "sleep", lambda _s: None)
    results = [
        RunResult(success=False, stdout="", stderr="Invalid argument", returncode=1),
        RunResult(success=True, stdout="ok", stderr="", returncode=0),
    ]
    calls = {"n": 0}

    def fake_run(cmd, timeout=tc._RUN_TIMEOUT):
        r = results[calls["n"]]
        calls["n"] += 1
        return r

    monkeypatch.setattr(tc, "_run", fake_run)
    out = tc.compile_sketch(tmp_path, "esp32:esp32:esp32")
    assert out.success
    assert calls["n"] == 2


def test_compile_sketch_does_not_retry_compile_error(tmp_path, monkeypatch):
    import nff.tools.toolchain as tc
    monkeypatch.setattr(tc, "find_arduino_cli", lambda: "/fake/cli")
    monkeypatch.setattr(tc._retry.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def fake_run(cmd, timeout=tc._RUN_TIMEOUT):
        calls["n"] += 1
        return RunResult(success=False, stdout="sketch.ino: error: expected ';'",
                         stderr="", returncode=1)

    monkeypatch.setattr(tc, "_run", fake_run)
    out = tc.compile_sketch(tmp_path, "esp32:esp32:esp32")
    assert not out.success
    assert calls["n"] == 1  # genuine compile error fails fast


def test_stream_with_retry_retries_transient(monkeypatch):
    import nff.tools.toolchain as tc

    class _FakeStream:
        def __init__(self, lines, rc):
            self._lines, self.returncode = lines, rc
        def __iter__(self):
            yield from self._lines

    streams = [
        _FakeStream(["Invalid argument"], 1),
        _FakeStream(["uploading", "done"], 0),
    ]
    made = {"n": 0}

    def make_stream():
        s = streams[made["n"]]
        made["n"] += 1
        return s

    monkeypatch.setattr(tc._retry.time, "sleep", lambda _s: None)
    emitted = []
    rc = tc.stream_with_retry(make_stream, emitted.append)
    assert rc == 0
    assert made["n"] == 2
    assert any("retrying" in line for line in emitted)


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
    monkeypatch.setattr("nff.tools.toolchain._arduino_cli_fallback_path", lambda: None)
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
# resolve_sketch_dir — file / folder / code normalisation
# ---------------------------------------------------------------------------

def test_resolve_sketch_dir_accepts_folder(tmp_path):
    sketch = tmp_path / "blink"
    sketch.mkdir()
    (sketch / "blink.ino").write_text("void setup(){}")
    assert resolve_sketch_dir(source=sketch) == sketch


def test_resolve_sketch_dir_folder_without_ino_raises(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ToolchainError, match="No .ino"):
        resolve_sketch_dir(source=empty)


def test_resolve_sketch_dir_ino_with_matching_parent(tmp_path):
    sketch = tmp_path / "blink"
    sketch.mkdir()
    ino = sketch / "blink.ino"
    ino.write_text("void setup(){}")
    assert resolve_sketch_dir(source=ino) == sketch


def test_resolve_sketch_dir_loose_ino_is_copied_into_named_folder(tmp_path):
    loose = tmp_path / "blink.ino"
    loose.write_text("void loop(){}")
    dest = tmp_path / "out"
    result = resolve_sketch_dir(source=loose, sketch_dir=dest)
    assert (result / f"{result.name}.ino").read_text() == "void loop(){}"


def test_resolve_sketch_dir_from_code(tmp_path):
    result = resolve_sketch_dir(code="void setup(){}", sketch_dir=tmp_path / "s")
    assert (result / "s.ino").read_text() == "void setup(){}"


def test_resolve_sketch_dir_requires_some_input():
    with pytest.raises(ToolchainError, match="either code"):
        resolve_sketch_dir()


# ---------------------------------------------------------------------------
# discover_artifacts / elf_path_for — deterministic build layout
# ---------------------------------------------------------------------------

def test_elf_path_for_uses_dotted_fqbn(tmp_path):
    sd = tmp_path / "blink"
    sd.mkdir()
    elf = elf_path_for(sd, "esp32:esp32:esp32")
    assert elf == sd / "build" / "esp32.esp32.esp32" / "blink.ino.elf"


def test_discover_artifacts_finds_elf_and_image(tmp_path):
    sd = tmp_path / "blink"
    build = sd / "build" / "esp32.esp32.esp32"
    build.mkdir(parents=True)
    (build / "blink.ino.elf").write_bytes(b"elf")
    (build / "blink.ino.bin").write_bytes(b"bin")
    (build / "blink.ino.merged.bin").write_bytes(b"merged")
    arts = discover_artifacts(sd, "esp32:esp32:esp32")
    assert arts["elf"].name == "blink.ino.elf"
    assert arts["merged_bin"].name == "blink.ino.merged.bin"


def test_discover_artifacts_empty_when_nothing_built(tmp_path):
    sd = tmp_path / "blink"
    sd.mkdir()
    assert discover_artifacts(sd, "esp32:esp32:esp32") == {}


# ---------------------------------------------------------------------------
# compile_only — structured, port-free compile
# ---------------------------------------------------------------------------

def test_compile_only_requires_fqbn():
    with pytest.raises(ToolchainError, match="FQBN"):
        compile_only("", code="void setup(){}")


def test_compile_only_requires_arduino_cli(monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli", lambda: None)
    with pytest.raises(ToolchainError, match="arduino-cli not found"):
        compile_only("arduino:avr:uno", code="void setup(){}")


def test_compile_only_success_collects_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli", lambda: "/fake/cli")

    def fake_compile(sd, fqbn):
        build = sd / "build" / fqbn.replace(":", ".")
        build.mkdir(parents=True, exist_ok=True)
        (build / f"{sd.name}.ino.elf").write_bytes(b"elf")
        (build / f"{sd.name}.ino.merged.bin").write_bytes(b"bin")
        return _ok_result(stdout="Sketch uses 1000 bytes (3%)")

    monkeypatch.setattr("nff.tools.toolchain.compile_sketch", fake_compile)
    result = compile_only("esp32:esp32:esp32", code="void setup(){}",
                          sketch_dir=tmp_path / "blink")
    assert isinstance(result, CompileResult)
    assert result.ok
    assert result.elf is not None and result.elf.suffix == ".elf"
    assert result.image is not None and result.image.name.endswith(".merged.bin")
    assert "OK: compile succeeded" in result.summary()


def test_compile_only_failure_reports_errors(tmp_path, monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli", lambda: "/fake/cli")
    monkeypatch.setattr("nff.tools.toolchain.compile_sketch",
                        lambda sd, fqbn: _fail_result(stderr="blink.ino:3:1: error: expected ';'"))
    result = compile_only("arduino:avr:uno", code="void setup(){", sketch_dir=tmp_path / "blink")
    assert not result.ok
    assert result.elf is None
    assert any("error:" in e for e in result.errors)
    assert result.summary().startswith("ERROR:")


def test_compile_only_accepts_a_folder(tmp_path, monkeypatch):
    monkeypatch.setattr("nff.tools.toolchain.find_arduino_cli", lambda: "/fake/cli")
    sketch = tmp_path / "blink"
    sketch.mkdir()
    (sketch / "blink.ino").write_text("void setup(){}")
    monkeypatch.setattr("nff.tools.toolchain.compile_sketch",
                        lambda sd, fqbn: _ok_result(stdout="ok"))
    result = compile_only("arduino:avr:uno", source=sketch)
    assert result.sketch_dir == sketch
    assert result.ok


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
