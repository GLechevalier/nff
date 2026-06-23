"""Tests for the PlatformIO build backend and toolchain dispatch."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from nff.commands.clean import clean
from nff.tools import toolchain
from nff.tools.backends import platformio as pio


# ---------------------------------------------------------------------------
# backend selection / dispatch
# ---------------------------------------------------------------------------

def test_active_backend_defaults_to_platformio(isolated_config, monkeypatch):
    monkeypatch.delenv("NFF_BUILD_BACKEND", raising=False)
    assert toolchain.active_backend() == "platformio"


def test_active_backend_arduino_when_explicit(isolated_config, monkeypatch):
    monkeypatch.setenv("NFF_BUILD_BACKEND", "arduino")
    assert toolchain.active_backend() == "arduino"


def test_active_backend_env_overrides(isolated_config, monkeypatch):
    monkeypatch.setenv("NFF_BUILD_BACKEND", "platformio")
    assert toolchain.active_backend() == "platformio"
    monkeypatch.setenv("NFF_BUILD_BACKEND", "pio")  # alias
    assert toolchain.active_backend() == "platformio"


def test_active_backend_from_config(isolated_config, monkeypatch):
    from nff import config
    monkeypatch.delenv("NFF_BUILD_BACKEND", raising=False)
    config.set_build_backend("platformio")
    assert toolchain.active_backend() == "platformio"


def test_configured_board_prefers_build_board_for_pio(isolated_config, monkeypatch):
    from nff import config
    monkeypatch.setenv("NFF_BUILD_BACKEND", "platformio")
    config.set_default_device("COM3", "ESP32", "esp32:esp32:esp32", 115200)
    config.set_build_board("esp32dev")
    assert toolchain.configured_board() == "esp32dev"


def test_configured_board_uses_fqbn_for_arduino(isolated_config, monkeypatch):
    from nff import config
    monkeypatch.setenv("NFF_BUILD_BACKEND", "arduino")
    config.set_default_device("COM3", "ESP32", "esp32:esp32:esp32", 115200)
    assert toolchain.configured_board() == "esp32:esp32:esp32"


# ---------------------------------------------------------------------------
# project scaffolding
# ---------------------------------------------------------------------------

def test_resolve_project_writes_main_cpp_with_arduino_header(tmp_path):
    proj = tmp_path / "proj"
    pio.resolve_project(code="void setup(){}\nvoid loop(){}\n", sketch_dir=proj)
    main = proj / "src" / "main.cpp"
    assert main.exists()
    text = main.read_text(encoding="utf-8")
    assert text.startswith("#include <Arduino.h>")
    assert "void setup()" in text


def test_resolve_project_does_not_duplicate_arduino_header(tmp_path):
    proj = tmp_path / "proj"
    code = "#include <Arduino.h>\nvoid setup(){}\n"
    pio.resolve_project(code=code, sketch_dir=proj)
    text = (proj / "src" / "main.cpp").read_text(encoding="utf-8")
    assert text.count("#include <Arduino.h>") == 1


def test_resolve_project_reads_ino_source(tmp_path):
    ino = tmp_path / "blink.ino"
    ino.write_text("void setup(){}\n", encoding="utf-8")
    proj = pio.resolve_project(source=ino, sketch_dir=tmp_path / "out")
    assert (proj / "src" / "main.cpp").read_text(encoding="utf-8").endswith("void setup(){}\n")


def test_resolve_project_uses_existing_pio_project_as_is(tmp_path):
    existing = tmp_path / "myproj"
    (existing / "src").mkdir(parents=True)
    (existing / "platformio.ini").write_text("[env:nff]\n", encoding="utf-8")
    assert pio.resolve_project(source=existing) == existing


def test_resolve_project_skips_nff_lib_when_unused(tmp_path):
    proj = tmp_path / "proj"
    with patch("nff.tools.arduino_lib.install_nff_library") as minstall:
        pio.resolve_project(code="void setup(){}\n", sketch_dir=proj)
    minstall.assert_not_called()
    assert not (proj / "lib" / "nff").exists()


def test_resolve_project_materializes_nff_lib_when_used(tmp_path):
    proj = tmp_path / "proj"
    with patch("nff.tools.arduino_lib.install_nff_library") as minstall:
        pio.resolve_project(code="#include <nff.h>\nvoid setup(){}\n", sketch_dir=proj)
    minstall.assert_called_once()
    assert minstall.call_args.kwargs["dest"] == proj / "lib" / "nff"


# ---------------------------------------------------------------------------
# platformio.ini generation
# ---------------------------------------------------------------------------

def test_write_platformio_ini_embeds_board_platform_and_token(tmp_path):
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "main.cpp").write_text("void setup(){}\n", encoding="utf-8")
    pio.write_platformio_ini(proj, "esp32dev")
    ini = (proj / "platformio.ini").read_text(encoding="utf-8")
    assert "board = esp32dev" in ini
    assert "platform = espressif32" in ini
    assert "framework = arduino" in ini
    assert "-DNFF_FQBN_TOKEN=esp32dev" in ini
    # No PubSubClient reference => no lib_deps line.
    assert "lib_deps" not in ini


def test_write_platformio_ini_adds_lib_deps_when_referenced(tmp_path):
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "main.cpp").write_text(
        "#include <PubSubClient.h>\nvoid setup(){}\n", encoding="utf-8")
    pio.write_platformio_ini(proj, "esp32dev")
    ini = (proj / "platformio.ini").read_text(encoding="utf-8")
    assert "lib_deps" in ini
    assert "knolleary/PubSubClient" in ini


def test_write_platformio_ini_omits_platform_for_unknown_board(tmp_path):
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "main.cpp").write_text("void setup(){}\n", encoding="utf-8")
    pio.write_platformio_ini(proj, "some_exotic_board")
    ini = (proj / "platformio.ini").read_text(encoding="utf-8")
    assert "board = some_exotic_board" in ini
    assert "platform =" not in ini  # unknown → let PlatformIO resolve it


# ---------------------------------------------------------------------------
# artifact discovery
# ---------------------------------------------------------------------------

def test_discover_artifacts_maps_pio_layout(tmp_path):
    build = tmp_path / ".pio" / "build" / "nff"
    build.mkdir(parents=True)
    (build / "firmware.elf").write_bytes(b"\x7fELF")
    (build / "firmware.bin").write_bytes(b"\x00")
    arts = pio.discover_artifacts(tmp_path, "esp32dev")
    assert arts["elf"].name == "firmware.elf"
    assert arts["bin"].name == "firmware.bin"


def test_discover_artifacts_empty_when_no_build(tmp_path):
    assert pio.discover_artifacts(tmp_path, "esp32dev") == {}


# ---------------------------------------------------------------------------
# tool discovery
# ---------------------------------------------------------------------------

def test_find_platformio_uses_path(monkeypatch):
    monkeypatch.setattr("nff.tools.backends.platformio.shutil.which",
                        lambda exe: "/usr/bin/pio" if exe == "pio" else None)
    assert pio.find_platformio() == ["/usr/bin/pio"]


def test_find_platformio_falls_back_to_module(monkeypatch):
    monkeypatch.setattr("nff.tools.backends.platformio.shutil.which", lambda exe: None)
    monkeypatch.setattr(Path, "exists", lambda self: False)
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    cmd = pio.find_platformio()
    assert cmd[-2:] == ["-m", "platformio"]


# ---------------------------------------------------------------------------
# compile dispatch end-to-end (subprocess mocked)
# ---------------------------------------------------------------------------

def test_compile_only_dispatches_to_pio(isolated_config, monkeypatch, tmp_path):
    monkeypatch.setenv("NFF_BUILD_BACKEND", "platformio")
    monkeypatch.setattr(pio, "find_platformio", lambda: ["pio"])

    ran = {}

    def fake_run(cmd, timeout=None):
        ran["cmd"] = cmd
        # Simulate a successful build producing artifacts.
        proj = Path(cmd[cmd.index("-d") + 1])
        build = proj / ".pio" / "build" / "nff"
        build.mkdir(parents=True, exist_ok=True)
        (build / "firmware.elf").write_bytes(b"\x7fELF")
        (build / "firmware.bin").write_bytes(b"\x00")
        return toolchain.RunResult(success=True, stdout="ok", stderr="", returncode=0)

    monkeypatch.setattr(toolchain, "_run", fake_run)
    result = toolchain.compile_only("esp32dev", code="void setup(){}\nvoid loop(){}\n")
    assert result.ok
    assert result.fqbn == "esp32dev"
    assert result.elf is not None and result.elf.name == "firmware.elf"
    assert "run" in ran["cmd"] and "esp32dev" not in ran["cmd"]  # board lives in the ini


# ---------------------------------------------------------------------------
# #1 — a user-provided platformio.ini is respected (BYO projects)
# ---------------------------------------------------------------------------

def test_write_platformio_ini_preserves_byo_ini(tmp_path):
    proj = tmp_path / "myproj"  # NOT under _PIO_DIR -> a BYO project
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "main.cpp").write_text("void setup(){}\n", encoding="utf-8")
    custom = "[env:myboard]\nboard = esp32dev\nboard_build.partitions = huge_app.csv\n"
    (proj / "platformio.ini").write_text(custom, encoding="utf-8")
    pio.write_platformio_ini(proj, "esp32dev")
    assert (proj / "platformio.ini").read_text(encoding="utf-8") == custom


def test_compile_cmd_pins_env_for_scaffold(monkeypatch, tmp_path):
    monkeypatch.setattr(pio, "_PIO_DIR", tmp_path / "nff_pio")
    monkeypatch.setattr(pio, "find_platformio", lambda: ["pio"])
    proj = pio._PIO_DIR / "sketch"
    proj.mkdir(parents=True)
    cmd = pio._compile_cmd(proj)
    assert "-e" in cmd and "nff" in cmd


def test_compile_cmd_omits_env_for_byo(monkeypatch, tmp_path):
    monkeypatch.setattr(pio, "find_platformio", lambda: ["pio"])
    proj = tmp_path / "myproj"  # NOT under _PIO_DIR
    proj.mkdir()
    cmd = pio._compile_cmd(proj)
    assert "-e" not in cmd


# ---------------------------------------------------------------------------
# #3 — multi-file sketch folders
# ---------------------------------------------------------------------------

def test_resolve_project_copies_multifile_sketch(tmp_path):
    sketch = tmp_path / "blinker"
    sketch.mkdir()
    (sketch / "blinker.ino").write_text(
        '#include "helper.h"\nvoid setup(){ help(); }\n', encoding="utf-8")
    (sketch / "helper.cpp").write_text(
        '#include "helper.h"\nvoid help(){}\n', encoding="utf-8")
    (sketch / "helper.h").write_text("void help();\n", encoding="utf-8")
    proj = pio.resolve_project(source=sketch, sketch_dir=tmp_path / "out")
    src = proj / "src"
    assert (src / "blinker.ino").exists()
    assert (src / "helper.cpp").exists()
    assert (src / "helper.h").exists()


def test_write_platformio_ini_detects_lib_dep_in_helper(tmp_path):
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "main.cpp").write_text("void setup(){}\n", encoding="utf-8")
    (proj / "src" / "net.cpp").write_text(
        "#include <PubSubClient.h>\n", encoding="utf-8")
    pio.write_platformio_ini(proj, "esp32dev")
    ini = (proj / "platformio.ini").read_text(encoding="utf-8")
    assert "knolleary/PubSubClient" in ini


# ---------------------------------------------------------------------------
# #4 — package-fault auto-repair between retries
# ---------------------------------------------------------------------------

def test_recover_packages_prunes_on_package_error(monkeypatch):
    monkeypatch.setattr(pio, "find_platformio", lambda: ["pio"])
    calls = []
    monkeypatch.setattr(toolchain, "_run", lambda cmd, timeout=None: calls.append(cmd))
    pio._recover_packages("package-manager-ioerror", "esp32dev", emit=lambda _m: None)
    assert calls and "uninstall" in calls[0] and "espressif32" in calls[0]


def test_recover_packages_noop_without_signature(monkeypatch):
    calls = []
    monkeypatch.setattr(toolchain, "_run", lambda cmd, timeout=None: calls.append(cmd))
    pio._recover_packages("error: expected ';'", "esp32dev", emit=lambda _m: None)
    assert calls == []


# ---------------------------------------------------------------------------
# #2 — nff clean removes both arduino and PlatformIO temp dirs
# ---------------------------------------------------------------------------

def test_clean_removes_arduino_and_pio_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    (tmp_path / "nff_sketch").mkdir()
    (tmp_path / "nff_pio" / "proj" / ".pio" / "build").mkdir(parents=True)
    result = CliRunner().invoke(clean)
    assert result.exit_code == 0
    assert not (tmp_path / "nff_sketch").exists()
    assert not (tmp_path / "nff_pio").exists()
