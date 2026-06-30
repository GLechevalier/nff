"""Tests for the live on-chip debug bridge (nff.tools.debug + MCP handlers).

No real hardware, OpenOCD, GDB, or pygdbmi is needed: the GDB controller is replaced
with a FakeGdb that returns canned MI responses, and OpenOCD startup is stubbed out.
"""

import pytest

from nff.tools import debug as dbg
from nff.tools.backends import platformio as pio


# ---------------------------------------------------------------------------
# MI response builders + a fake pygdbmi GdbController
# ---------------------------------------------------------------------------

def _done(payload):
    return [{"type": "result", "message": "done", "payload": payload}]


def _error(msg):
    return [{"type": "result", "message": "error", "payload": {"msg": msg}}]


def _console(text):
    return [
        {"type": "console", "payload": text},
        {"type": "result", "message": "done", "payload": {}},
    ]


class FakeGdb:
    """Routes MI commands (by startswith prefix) to canned responses."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.writes = []
        self.exited = False

    def write(self, command, timeout_sec=None):
        self.writes.append(command)
        for prefix, resp in self.routes.items():
            if command.startswith(prefix):
                return resp(command) if callable(resp) else resp
        return _done({})

    def exit(self):
        self.exited = True


def _session_with(routes=None, halted=True):
    """A DebugSession wired to a FakeGdb, bypassing start()/OpenOCD."""
    from pathlib import Path

    s = dbg.DebugSession("esp32s3", Path("firmware.elf"), "openocd", "gdb", ["-f", "x.cfg"])
    s._gdb = FakeGdb(routes)
    s.halted = halted
    return s


@pytest.fixture(autouse=True)
def _debug_env(isolated_config, monkeypatch):
    """Reset the module singleton and isolate config for every test."""
    dbg._SESSION = None
    yield
    dbg._SESSION = None


# ---------------------------------------------------------------------------
# Chip detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("board,expected", [
    ("esp32-s3-devkitc-1", "esp32s3"),
    ("esp32:esp32:esp32s3", "esp32s3"),
    ("esp32-c3-devkitm-1", "esp32c3"),
    ("esp32-c6-devkitc-1", "esp32c6"),
    ("esp32-s2-saola-1", "esp32s2"),
    ("esp32dev", "esp32"),
    ("ESP32S3", "esp32s3"),
])
def test_detect_chip_from_board(board, expected, monkeypatch):
    monkeypatch.setattr(dbg.toolchain, "configured_board", lambda: "")
    monkeypatch.setattr(dbg.config, "get_default_device", lambda: {})
    assert dbg.detect_chip(board) == expected


def test_detect_chip_defaults_to_esp32(monkeypatch):
    monkeypatch.setattr(dbg.toolchain, "configured_board", lambda: "")
    monkeypatch.setattr(dbg.config, "get_default_device", lambda: {})
    assert dbg.detect_chip() == "esp32"


def test_detect_chip_uses_configured_board(monkeypatch):
    monkeypatch.setattr(dbg.toolchain, "configured_board", lambda: "esp32-c6-devkitc-1")
    monkeypatch.setattr(dbg.config, "get_default_device", lambda: {})
    assert dbg.detect_chip() == "esp32c6"


@pytest.mark.parametrize("board,expected", [
    ("nucleo_f401re", "stm32f4"),
    ("STMicroelectronics:stm32:Nucleo_64", "stm32"),
    ("genericSTM32F103C8", "stm32f1"),
    ("bluepill_f103c8", "stm32f1"),
])
def test_detect_chip_stm32(board, expected, monkeypatch):
    monkeypatch.setattr(dbg.toolchain, "configured_board", lambda: "")
    monkeypatch.setattr(dbg.config, "get_default_device", lambda: {})
    assert dbg.detect_chip(board) == expected


def test_detect_chip_stm32_from_fqbn_plus_pio_board(monkeypatch):
    # Real Nucleo case: fqbn says stm32, configured pio board carries the F4 family.
    monkeypatch.setattr(dbg.toolchain, "configured_board", lambda: "nucleo_f401re")
    monkeypatch.setattr(dbg.config, "get_default_device",
                        lambda: {"fqbn": "STMicroelectronics:stm32:Nucleo_64"})
    assert dbg.detect_chip() == "stm32f4"


def test_family():
    assert dbg._family("stm32f4") == "arm"
    assert dbg._family("esp32c3") == "riscv"
    assert dbg._family("esp32s3") == "xtensa"
    assert dbg._family("esp32") == "xtensa"


# ---------------------------------------------------------------------------
# Binary / config discovery
# ---------------------------------------------------------------------------

def test_find_openocd_prefers_platformio(tmp_path, monkeypatch):
    pkgs = tmp_path / "packages"
    binname = "openocd.exe" if dbg.sys.platform == "win32" else "openocd"
    ocd = pkgs / "tool-openocd-esp32" / "bin" / binname
    ocd.parent.mkdir(parents=True)
    ocd.write_text("x")
    monkeypatch.setattr(dbg, "_platformio_packages", lambda: pkgs)
    assert dbg.find_openocd() == str(ocd)


def test_find_openocd_falls_back_to_path(tmp_path, monkeypatch):
    monkeypatch.setattr(dbg, "_platformio_packages", lambda: tmp_path / "nope")
    monkeypatch.setattr(dbg.shutil, "which", lambda name: "/usr/bin/openocd")
    assert dbg.find_openocd() == "/usr/bin/openocd"


def test_find_openocd_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dbg, "_platformio_packages", lambda: tmp_path / "nope")
    monkeypatch.setattr(dbg.shutil, "which", lambda name: None)
    assert dbg.find_openocd() is None


def test_find_gdb_riscv(tmp_path, monkeypatch):
    pkgs = tmp_path / "packages"
    gdb = pkgs / "toolchain-riscv32-esp" / "bin" / "riscv32-esp-elf-gdb"
    gdb.parent.mkdir(parents=True)
    gdb.write_text("x")
    monkeypatch.setattr(dbg, "_platformio_packages", lambda: pkgs)
    assert dbg.find_gdb("esp32c3") == str(gdb)


def test_find_gdb_xtensa(tmp_path, monkeypatch):
    pkgs = tmp_path / "packages"
    gdb = pkgs / "toolchain-xtensa-esp-elf" / "bin" / "xtensa-esp-elf-gdb"
    gdb.parent.mkdir(parents=True)
    gdb.write_text("x")
    monkeypatch.setattr(dbg, "_platformio_packages", lambda: pkgs)
    assert dbg.find_gdb("esp32s3") == str(gdb)


def test_find_gdb_skips_helper_scripts(tmp_path, monkeypatch):
    """A …-gdb-add-index helper must not be mistaken for the gdb binary."""
    pkgs = tmp_path / "packages"
    bindir = pkgs / "toolchain-xtensa-esp32" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "xtensa-esp32-elf-gdb-add-index").write_text("x")
    real = bindir / "xtensa-esp32-elf-gdb"
    real.write_text("x")
    monkeypatch.setattr(dbg, "_platformio_packages", lambda: pkgs)
    assert dbg.find_gdb("esp32") == str(real)


def test_openocd_config_builtin():
    assert dbg.openocd_config("esp32s3") == ["-f", "board/esp32s3-builtin.cfg"]
    assert dbg.openocd_config("esp32c3") == ["-f", "board/esp32c3-builtin.cfg"]


def test_openocd_config_external_interface():
    assert dbg.openocd_config("esp32", interface="ftdi/esp32_devkitj_v1") == [
        "-f", "interface/ftdi/esp32_devkitj_v1.cfg", "-f", "target/esp32.cfg",
    ]


def test_openocd_config_classic_esp32_needs_interface():
    with pytest.raises(dbg.DebugError) as exc:
        dbg.openocd_config("esp32")
    assert "no built-in USB-JTAG" in str(exc.value)


def test_openocd_config_stm32_stlink():
    assert dbg.openocd_config("stm32f4") == [
        "-f", "interface/stlink.cfg", "-f", "target/stm32f4x.cfg",
    ]
    assert dbg.openocd_config("stm32f1") == [
        "-f", "interface/stlink.cfg", "-f", "target/stm32f1x.cfg",
    ]


def test_openocd_config_stm32_unknown_family():
    with pytest.raises(dbg.DebugError) as exc:
        dbg.openocd_config("stm32")
    assert "unknown STM32 family" in str(exc.value)


def test_find_gdb_arm(tmp_path, monkeypatch):
    pkgs = tmp_path / "packages"
    bindir = pkgs / "toolchain-gccarmnoneeabi" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "arm-none-eabi-gdb-add-index").write_text("x")
    (bindir / "arm-none-eabi-gdb-py3").write_text("x")
    real = bindir / "arm-none-eabi-gdb"
    real.write_text("x")
    monkeypatch.setattr(dbg, "_platformio_packages", lambda: pkgs)
    assert dbg.find_gdb("stm32f4") == str(real)


def test_find_openocd_arm_prefers_generic(tmp_path, monkeypatch):
    pkgs = tmp_path / "packages"
    exe = "openocd.exe" if dbg.sys.platform == "win32" else "openocd"
    generic = pkgs / "tool-openocd" / "bin" / exe
    generic.parent.mkdir(parents=True)
    generic.write_text("x")
    esp = pkgs / "tool-openocd-esp32" / "bin" / exe
    esp.parent.mkdir(parents=True)
    esp.write_text("x")
    monkeypatch.setattr(dbg, "_platformio_packages", lambda: pkgs)
    assert dbg.find_openocd("stm32f4") == str(generic)
    assert dbg.find_openocd("esp32s3") == str(esp)


def test_openocd_scripts_dir(tmp_path):
    ocd = tmp_path / "tool-openocd" / "bin" / "openocd.exe"
    ocd.parent.mkdir(parents=True)
    ocd.write_text("x")
    scripts = tmp_path / "tool-openocd" / "openocd" / "scripts"
    scripts.mkdir(parents=True)
    assert dbg.openocd_scripts_dir(str(ocd)) == scripts


# ---------------------------------------------------------------------------
# ELF resolution
# ---------------------------------------------------------------------------

def test_resolve_elf_explicit(tmp_path):
    elf = tmp_path / "f.elf"
    elf.write_text("x")
    assert dbg.resolve_elf(str(elf)) == elf


def test_resolve_elf_explicit_missing(tmp_path):
    with pytest.raises(dbg.DebugError):
        dbg.resolve_elf(str(tmp_path / "missing.elf"))


def test_resolve_elf_from_pio_build(tmp_path, monkeypatch):
    build = tmp_path / "nff_pio" / "sketch" / ".pio" / "build" / "nff"
    build.mkdir(parents=True)
    elf = build / "firmware.elf"
    elf.write_text("x")
    monkeypatch.setattr(pio, "_PIO_DIR", tmp_path / "nff_pio")
    assert dbg.resolve_elf() == elf


def test_resolve_elf_none_found(tmp_path, monkeypatch):
    monkeypatch.setattr(pio, "_PIO_DIR", tmp_path / "empty")
    monkeypatch.setattr(dbg.toolchain.tempfile, "gettempdir", lambda: str(tmp_path / "alsoempty"))
    with pytest.raises(dbg.DebugError) as exc:
        dbg.resolve_elf()
    assert "No firmware ELF" in str(exc.value)


# ---------------------------------------------------------------------------
# MI helpers
# ---------------------------------------------------------------------------

def test_result_returns_payload():
    assert dbg._result(_done({"a": 1})) == {"a": 1}


def test_result_raises_on_error():
    with pytest.raises(dbg.DebugError) as exc:
        dbg._result(_error("bad expr"))
    assert "bad expr" in str(exc.value)


def test_console_text_concatenates():
    responses = [
        {"type": "console", "payload": "hello "},
        {"type": "log", "payload": "world"},
        {"type": "result", "message": "done", "payload": {}},
    ]
    assert dbg._console_text(responses) == "hello world"


def test_hex_dump():
    out = dbg._hex_dump("0x3ffb0000", "0011223344556677")
    assert out == "0x3ffb0000: 00 11 22 33 44 55 66 77"


# ---------------------------------------------------------------------------
# DebugSession introspection
# ---------------------------------------------------------------------------

def test_registers():
    s = _session_with({
        "-data-list-register-names": _done({"register-names": ["pc", "", "a0"]}),
        "-data-list-register-values": _done({"register-values": [
            {"number": "0", "value": "0x40080000"},
            {"number": "2", "value": "0x1"},
        ]}),
    })
    assert s.registers() == {"registers": {"pc": "0x40080000", "a0": "0x1"}}


def test_call_stack():
    s = _session_with({
        "-stack-list-frames": _done({"stack": [
            {"level": "0", "func": "loop", "file": "main.cpp", "line": "12", "addr": "0x4008"},
            {"level": "1", "func": "app_main", "file": "main.cpp", "line": "30", "addr": "0x4009"},
        ]}),
    })
    out = s.call_stack()
    assert out["frames"][0] == {
        "level": "0", "function": "loop", "file": "main.cpp", "line": "12", "address": "0x4008",
    }
    assert out["frames"][1]["function"] == "app_main"


def test_variables_selects_frame():
    s = _session_with({
        "-stack-list-variables": _done({"variables": [
            {"name": "x", "value": "5"}, {"name": "y", "value": "7"},
        ]}),
    })
    out = s.variables(2)
    assert out == {"frame": 2, "variables": [{"name": "x", "value": "5"}, {"name": "y", "value": "7"}]}
    assert "-stack-select-frame 2" in s._gdb.writes


def test_evaluate():
    s = _session_with({"-data-evaluate-expression": _done({"value": "42"})})
    assert s.evaluate("counter") == {"expression": "counter", "value": "42"}


def test_memory_hex_dump():
    s = _session_with({"-data-read-memory-bytes": _done({"memory": [
        {"begin": "0x3ffb0000", "contents": "deadbeef"},
    ]})})
    out = s.memory("0x3ffb0000", 4)
    assert out["hex"] == "deadbeef"
    assert out["dump"] == "0x3ffb0000: de ad be ef"


def test_set_breakpoint():
    s = _session_with({"-break-insert": _done({"bkpt": {
        "number": "1", "func": "loop", "file": "main.cpp", "line": "12", "addr": "0x4008",
    }})}, halted=False)
    out = s.set_breakpoint("loop")
    assert out["number"] == "1"
    assert out["function"] == "loop"


def test_expand_variable():
    s = _session_with({
        "-var-create": _done({"name": "var1", "value": "{...}", "type": "Point"}),
        "-var-list-children": _done({"children": [
            {"exp": "x", "value": "1", "type": "int"},
            {"exp": "y", "value": "2", "type": "int"},
        ]}),
        "-var-delete": _done({}),
    })
    out = s.expand_variable("pt")
    assert out["type"] == "Point"
    assert out["children"] == [
        {"name": "x", "value": "1", "type": "int"},
        {"name": "y", "value": "2", "type": "int"},
    ]
    assert any(w.startswith("-var-delete") for w in s._gdb.writes)


def test_gdb_command_mi():
    s = _session_with({"-data-list-register-names": _done({"register-names": ["pc"]})})
    out = s.gdb_command("-data-list-register-names")
    assert out["result"] == {"register-names": ["pc"]}


def test_gdb_command_console():
    s = _session_with({"-interpreter-exec": _console("Reset cause: 1\n")})
    out = s.gdb_command("monitor reg pc")
    assert out["output"] == "Reset cause: 1\n"


def test_step_kinds():
    s = _session_with({"-stack-info-frame": _done({"frame": {}})})
    s.step("over")
    assert "-exec-next" in s._gdb.writes
    s.step("into")
    assert "-exec-step" in s._gdb.writes
    s.step("out")
    assert "-exec-finish" in s._gdb.writes


def test_step_unknown_kind():
    s = _session_with()
    with pytest.raises(dbg.DebugError):
        s.step("sideways")


def test_pause_and_continue_toggle_halted():
    s = _session_with({"-stack-info-frame": _done({"frame": {}})}, halted=False)
    s.pause()
    assert s.halted is True
    s.cont()
    assert s.halted is False


def test_introspection_requires_halt():
    s = _session_with(halted=False)
    with pytest.raises(dbg.DebugError) as exc:
        s.registers()
    assert "running" in str(exc.value)


# ---------------------------------------------------------------------------
# Lifecycle / singleton
# ---------------------------------------------------------------------------

def _stub_start(monkeypatch):
    monkeypatch.setattr(dbg, "find_openocd", lambda chip=None: "openocd")
    monkeypatch.setattr(dbg, "find_gdb", lambda chip: "gdb")
    monkeypatch.setattr(dbg, "resolve_elf", lambda elf=None: dbg.Path("firmware.elf"))
    monkeypatch.setattr(dbg, "_spawn_openocd", lambda o, c: object())
    monkeypatch.setattr(dbg, "_wait_for_gdb_server", lambda proc, deadline: None)
    monkeypatch.setattr(dbg, "_make_gdb_controller", lambda gdb: FakeGdb({
        "-stack-info-frame": _done({"frame": {"func": "loop", "file": "m.cpp", "line": "1", "addr": "0x1"}}),
    }))


def test_start_session_sets_singleton(monkeypatch):
    _stub_start(monkeypatch)
    info = dbg.start_session(board="esp32-s3-devkitc-1")
    assert info["chip"] == "esp32s3"
    assert info["halted"] is True
    assert dbg.get_session() is not None
    assert info["frame"]["function"] == "loop"


def test_start_session_replaces_previous(monkeypatch):
    _stub_start(monkeypatch)
    dbg.start_session(board="esp32-s3-devkitc-1")
    first = dbg.get_session()
    first_gdb = first._gdb
    dbg.start_session(board="esp32-s3-devkitc-1")
    assert dbg.get_session() is not first
    assert first_gdb.exited is True


def test_start_session_missing_openocd(monkeypatch):
    monkeypatch.setattr(dbg, "find_openocd", lambda chip=None: None)
    with pytest.raises(dbg.DebugError) as exc:
        dbg.start_session()
    assert "OpenOCD not found" in str(exc.value)


def test_start_session_missing_gdb(monkeypatch):
    monkeypatch.setattr(dbg, "find_openocd", lambda chip=None: "openocd")
    monkeypatch.setattr(dbg, "find_gdb", lambda chip: None)
    with pytest.raises(dbg.DebugError) as exc:
        dbg.start_session(board="esp32-s3-devkitc-1")
    assert "GDB" in str(exc.value)


def test_stop_session():
    assert dbg.stop_session() is False
    dbg._SESSION = _session_with()
    assert dbg.stop_session() is True
    assert dbg.get_session() is None


def test_require_session_raises_when_absent():
    with pytest.raises(dbg.DebugError):
        dbg.require_session()


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------

async def test_handler_get_session_info_no_session():
    from nff.mcp_server import get_session_info
    assert await get_session_info() == {"halted": False, "active": False}


async def test_handler_get_registers_no_session():
    from nff.mcp_server import get_registers
    out = await get_registers()
    assert isinstance(out, str) and out.startswith("ERROR: no active debug session")


async def test_handler_debug_stop_no_session():
    from nff.mcp_server import debug_stop
    assert await debug_stop() == "OK: no active debug session"


async def test_handler_debug_start_missing_openocd(monkeypatch):
    from nff.mcp_server import debug_start
    monkeypatch.setattr(dbg, "find_openocd", lambda chip=None: None)
    out = await debug_start()
    assert isinstance(out, str) and out.startswith("ERROR:")


async def test_handler_get_registers_with_session():
    from nff.mcp_server import get_registers
    dbg._SESSION = _session_with({
        "-data-list-register-names": _done({"register-names": ["pc"]}),
        "-data-list-register-values": _done({"register-values": [{"number": "0", "value": "0x1"}]}),
    })
    assert await get_registers() == {"registers": {"pc": "0x1"}}
