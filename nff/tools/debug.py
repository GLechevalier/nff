"""Live on-chip debugging for ESP32 — OpenOCD (JTAG) + GDB/MI bridge.

This is nff's equivalent of a Cortex-Debug bridge: it lets a caller halt a running
ESP32 and inspect it at the source level — registers, memory, local variables, the
call stack — set breakpoints, step, and run raw GDB. Unlike an IDE extension that
rides an existing debug session, nff owns the whole stack: it launches OpenOCD (a GDB
*server* on :3333), launches the chip's GDB in machine-interface (MI) mode, loads the
last build's ``firmware.elf`` for symbols, and ``reset halt``s the target.

A single :class:`DebugSession` is held as a module-level singleton (the running MCP
server process is long-lived, so the session persists across individual tool calls).
:func:`get_session` / :func:`require_session` mediate access; ``debug_start`` creates
the session and ``debug_stop`` tears it down.

Binaries are reused from PlatformIO's package cache (``~/.platformio/packages``) — the
same toolchain nff's default backend already installs — falling back to ``PATH``.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from nff import config
from nff.tools import toolchain
from nff.tools.backends import platformio as _pio

# GDB server port OpenOCD exposes for the espressif targets (its default).
_GDB_PORT = 3333
# How long to wait for OpenOCD to come up and start listening on _GDB_PORT.
_OPENOCD_STARTUP_TIMEOUT = 15.0
# Per-MI-command ceiling (seconds). reset/halt and a cold attach can be slow.
_MI_TIMEOUT = 20.0

# Chips with a built-in USB-Serial-JTAG controller — no external probe needed; OpenOCD
# ships a one-file ``board/<chip>-builtin.cfg`` for each. Classic esp32 / esp32s2 have
# no built-in JTAG and require an external adapter (the ``interface=`` override).
_BUILTIN_JTAG = frozenset({"esp32s3", "esp32c3", "esp32c6", "esp32c2", "esp32h2", "esp32p4"})

# Xtensa cores use xtensa-*-elf-gdb; the RISC-V parts use riscv32-esp-elf-gdb.
_RISCV_CHIPS = frozenset({"esp32c3", "esp32c6", "esp32c2", "esp32h2", "esp32p4"})

# Chip families, longest/most-specific token first so "esp32s3" wins over "esp32".
_CHIP_TOKENS = ("esp32s3", "esp32s2", "esp32c6", "esp32c3", "esp32c2", "esp32h2", "esp32p4", "esp32")


class DebugError(Exception):
    """A debug-session fault surfaced to the caller as ``ERROR: <msg>``."""


# ---------------------------------------------------------------------------
# Chip / board resolution
# ---------------------------------------------------------------------------

def detect_chip(board: Optional[str] = None) -> str:
    """Best-effort ESP32 chip family ("esp32s3", "esp32c3", … or "esp32").

    Looks at the passed board id/FQBN, else the configured board
    (:func:`toolchain.configured_board`), else the configured FQBN. Matching is on a
    normalised token (hyphens/colons stripped) so ``esp32-s3-devkitc-1``,
    ``esp32:esp32:esp32s3`` and ``esp32s3`` all resolve to ``esp32s3``.
    """
    candidates = [board or ""]
    try:
        candidates.append(toolchain.configured_board() or "")
    except Exception:
        pass
    try:
        candidates.append(config.get_default_device().get("fqbn") or "")
    except Exception:
        pass
    for raw in candidates:
        norm = raw.lower().replace("-", "").replace(":", "").replace("_", "")
        for token in _CHIP_TOKENS:
            if token in norm:
                return token
    return "esp32"


# ---------------------------------------------------------------------------
# Binary / config discovery (mirrors platformio.find_platformio idiom)
# ---------------------------------------------------------------------------

def _platformio_packages() -> Path:
    return Path.home() / ".platformio" / "packages"


def find_openocd() -> Optional[str]:
    """Path to an OpenOCD binary: PlatformIO's ``tool-openocd-esp32`` then ``PATH``."""
    override = (config.get_debug_config() or {}).get("openocd_path")
    if override and Path(override).exists():
        return override
    exe = "openocd.exe" if sys.platform == "win32" else "openocd"
    candidate = _platformio_packages() / "tool-openocd-esp32" / "bin" / exe
    if candidate.exists():
        return str(candidate)
    found = shutil.which("openocd")
    return found


def find_gdb(chip: str) -> Optional[str]:
    """Path to the GDB for ``chip``: PlatformIO's esp toolchain then ``PATH``.

    Xtensa parts (esp32/s2/s3) use ``xtensa-*-elf-gdb``; the RISC-V parts
    (c3/c6/h2/…) use ``riscv32-esp-elf-gdb``. Newer toolchains unify the xtensa GDB to
    ``xtensa-esp-elf-gdb``, so both the per-chip and the unified names are matched.
    """
    override = (config.get_debug_config() or {}).get("gdb_path")
    if override and Path(override).exists():
        return override
    if chip in _RISCV_CHIPS:
        patterns = ["*riscv32-esp-elf-gdb*"]
        path_names = ["riscv32-esp-elf-gdb"]
    else:
        patterns = [f"*xtensa-{chip}-elf-gdb*", "*xtensa-esp-elf-gdb*", "*xtensa-esp32-elf-gdb*"]
        path_names = [f"xtensa-{chip}-elf-gdb", "xtensa-esp-elf-gdb", "xtensa-esp32-elf-gdb"]
    pkgs = _platformio_packages()
    if pkgs.is_dir():
        for pattern in patterns:
            hits = sorted(pkgs.glob(f"toolchain-*/bin/{pattern}"))
            # The glob also matches helper scripts that merely start with the gdb name
            # (e.g. xtensa-esp32-elf-gdb-add-index, …-gdb-py) — keep only the binary
            # whose name actually ends in "gdb".
            for hit in hits:
                if hit.is_file() and hit.stem.endswith("gdb"):
                    return str(hit)
    for name in path_names:
        found = shutil.which(name)
        if found:
            return found
    return None


def openocd_config(chip: str, interface: Optional[str] = None) -> list[str]:
    """OpenOCD ``-f`` argument list for ``chip``.

    With no ``interface`` and a built-in-JTAG chip, uses the single
    ``board/<chip>-builtin.cfg``. An explicit ``interface`` (e.g. ``ftdi/esp32_devkitj_v1``
    or ``esp_usb_bridge``) pairs an ``interface/*.cfg`` with the chip's ``target/*.cfg``
    for external probes (and for classic esp32 / esp32s2, which have no built-in JTAG).
    """
    override = (config.get_debug_config() or {}).get("openocd_config")
    if override:
        return ["-f", override]
    if interface is None:
        interface = (config.get_debug_config() or {}).get("interface") or None
    if interface:
        return ["-f", f"interface/{interface}.cfg", "-f", f"target/{chip}.cfg"]
    if chip in _BUILTIN_JTAG:
        return ["-f", f"board/{chip}-builtin.cfg"]
    raise DebugError(
        f"{chip} has no built-in USB-JTAG — connect an external probe and pass "
        f"interface= (e.g. interface='ftdi/esp32_devkitj_v1'), or set debug.openocd_config"
    )


def resolve_elf(elf: Optional[str] = None) -> Path:
    """Locate the firmware ELF (symbol file) for the debug session.

    Explicit ``elf=`` wins. Otherwise the most-recently-built ``firmware.elf`` under
    the PlatformIO scratch tree is used (reusing the same build output
    :func:`platformio.discover_artifacts` reports), falling back to any ``*.elf`` an
    arduino-cli build left behind. Raises :class:`DebugError` if none is found.
    """
    if elf:
        p = Path(elf)
        if not p.exists():
            raise DebugError(f"ELF not found: {elf}")
        return p
    candidates: list[Path] = []
    pio_root = _pio._PIO_DIR
    if pio_root.is_dir():
        candidates.extend(p for p in pio_root.rglob("firmware.elf") if p.is_file())
    if not candidates:
        sketch_root = Path(toolchain.tempfile.gettempdir()) / "nff_sketch"
        if sketch_root.is_dir():
            candidates.extend(p for p in sketch_root.rglob("*.elf") if p.is_file())
    if not candidates:
        raise DebugError(
            "No firmware ELF found — compile first (`nff compile <sketch>`), "
            "or pass elf= with a path to a built .elf"
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------------------
# OpenOCD + GDB process management (injectable for tests)
# ---------------------------------------------------------------------------

def _spawn_openocd(openocd: str, cfg_args: list[str]) -> subprocess.Popen:
    """Launch OpenOCD as a GDB server. Overridable in tests."""
    return subprocess.Popen(
        [openocd, *cfg_args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )


def _make_gdb_controller(gdb: str):
    """Create a pygdbmi GdbController bound to ``gdb``. Overridable in tests."""
    from pygdbmi.gdbcontroller import GdbController

    return GdbController(command=[gdb, "--nx", "--quiet", "--interpreter=mi3"])


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_gdb_server(proc: subprocess.Popen, deadline: float) -> None:
    """Block until OpenOCD is listening on _GDB_PORT, or raise with its output."""
    while time.monotonic() < deadline:
        if _port_open("127.0.0.1", _GDB_PORT):
            return
        if proc.poll() is not None:
            out = ""
            try:
                if proc.stdout is not None:
                    out = proc.stdout.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise DebugError(f"OpenOCD exited before the GDB server came up:\n{out.strip()}")
        time.sleep(0.2)
    raise DebugError(f"OpenOCD did not start a GDB server on :{_GDB_PORT} within "
                     f"{_OPENOCD_STARTUP_TIMEOUT:.0f}s")


# ---------------------------------------------------------------------------
# MI response helpers
# ---------------------------------------------------------------------------

def _result(responses: list) -> dict:
    """Return the 'result' record's payload, raising DebugError on an MI error.

    pygdbmi yields a list of dicts (types: result/notify/console/log/…). The terminal
    ``result`` record carries ``message`` ('done'/'error'/…) and ``payload``.
    """
    error_msg = None
    for r in responses:
        if r.get("type") == "result":
            if r.get("message") == "error":
                payload = r.get("payload") or {}
                error_msg = payload.get("msg") or "GDB reported an error"
            else:
                return r.get("payload") or {}
    if error_msg is not None:
        raise DebugError(error_msg)
    return {}


def _console_text(responses: list) -> str:
    """Concatenate console/log stream output (for raw `info ...`-style commands)."""
    out = []
    for r in responses:
        if r.get("type") in ("console", "log", "output", "target"):
            payload = r.get("payload")
            if isinstance(payload, str):
                out.append(payload)
    return "".join(out)


# ---------------------------------------------------------------------------
# DebugSession
# ---------------------------------------------------------------------------

class DebugSession:
    """A live OpenOCD + GDB session against one ESP32 target."""

    def __init__(self, chip: str, elf: Path, openocd: str, gdb: str, cfg_args: list[str]):
        self.chip = chip
        self.elf = elf
        self.openocd_path = openocd
        self.gdb_path = gdb
        self.cfg_args = cfg_args
        self._openocd: Optional[subprocess.Popen] = None
        self._gdb = None
        self.halted = False

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> dict:
        self._openocd = _spawn_openocd(self.openocd_path, self.cfg_args)
        try:
            _wait_for_gdb_server(self._openocd, time.monotonic() + _OPENOCD_STARTUP_TIMEOUT)
            self._gdb = _make_gdb_controller(self.gdb_path)
            self._mi(f"-file-exec-and-symbols {self.elf.as_posix()!r}".replace("'", '"'))
            self._mi(f"-target-select remote 127.0.0.1:{_GDB_PORT}")
            self._mi('-interpreter-exec console "monitor reset halt"')
            self.halted = True
        except Exception:
            self.stop()
            raise
        return self.session_info()

    def stop(self) -> None:
        if self._gdb is not None:
            try:
                self._gdb.exit()
            except Exception:
                pass
            self._gdb = None
        if self._openocd is not None:
            try:
                self._openocd.terminate()
                try:
                    self._openocd.wait(timeout=5)
                except Exception:
                    self._openocd.kill()
            except Exception:
                pass
            self._openocd = None
        self.halted = False

    # -- low-level MI -------------------------------------------------------
    def _mi(self, command: str) -> list:
        if self._gdb is None:
            raise DebugError("GDB is not running")
        return self._gdb.write(command, timeout_sec=_MI_TIMEOUT)

    def _require_halted(self) -> None:
        if not self.halted:
            raise DebugError("target is running — call pause_execution first")

    # -- introspection ------------------------------------------------------
    def session_info(self) -> dict:
        info: dict = {"chip": self.chip, "elf": str(self.elf), "halted": self.halted}
        if self.halted:
            try:
                frame = _result(self._mi("-stack-info-frame")).get("frame", {})
                info["frame"] = {
                    "function": frame.get("func"),
                    "file": frame.get("file") or frame.get("fullname"),
                    "line": frame.get("line"),
                    "address": frame.get("addr"),
                }
            except DebugError:
                pass
        return info

    def call_stack(self) -> dict:
        self._require_halted()
        stack = _result(self._mi("-stack-list-frames")).get("stack", [])
        frames = []
        for entry in stack:
            f = entry if isinstance(entry, dict) else {}
            frames.append({
                "level": f.get("level"),
                "function": f.get("func"),
                "file": f.get("file") or f.get("fullname"),
                "line": f.get("line"),
                "address": f.get("addr"),
            })
        return {"frames": frames}

    def variables(self, frame: int = 0) -> dict:
        self._require_halted()
        self._mi(f"-stack-select-frame {int(frame)}")
        payload = _result(self._mi("-stack-list-variables --all-values"))
        variables = [
            {"name": v.get("name"), "value": v.get("value")}
            for v in payload.get("variables", [])
        ]
        return {"frame": int(frame), "variables": variables}

    def expand_variable(self, expression: str) -> dict:
        self._require_halted()
        created = _result(self._mi(f'-var-create - * "{expression}"'))
        name = created.get("name")
        result: dict = {
            "expression": expression,
            "value": created.get("value"),
            "type": created.get("type"),
            "children": [],
        }
        try:
            kids = _result(self._mi(f'-var-list-children --all-values "{name}"'))
            for child in kids.get("children", []):
                c = child if isinstance(child, dict) else {}
                result["children"].append({
                    "name": c.get("exp"),
                    "value": c.get("value"),
                    "type": c.get("type"),
                })
        finally:
            if name:
                try:
                    self._mi(f'-var-delete "{name}"')
                except DebugError:
                    pass
        return result

    def registers(self) -> dict:
        self._require_halted()
        names = _result(self._mi("-data-list-register-names")).get("register-names", [])
        values = _result(self._mi("-data-list-register-values x")).get("register-values", [])
        regs = {}
        for entry in values:
            num = entry.get("number")
            try:
                idx = int(num)
            except (TypeError, ValueError):
                continue
            name = names[idx] if 0 <= idx < len(names) else None
            if name:
                regs[name] = entry.get("value")
        return {"registers": regs}

    def memory(self, address: str, count: int = 64) -> dict:
        self._require_halted()
        payload = _result(self._mi(f"-data-read-memory-bytes {address} {int(count)}"))
        blocks = payload.get("memory", [])
        contents = blocks[0].get("contents", "") if blocks else ""
        begin = blocks[0].get("begin") if blocks else address
        return {
            "address": address,
            "begin": begin,
            "count": int(count),
            "hex": contents,
            "dump": _hex_dump(begin, contents),
        }

    def evaluate(self, expression: str) -> dict:
        self._require_halted()
        payload = _result(self._mi(f'-data-evaluate-expression "{expression}"'))
        return {"expression": expression, "value": payload.get("value")}

    def set_breakpoint(self, location: str) -> dict:
        payload = _result(self._mi(f"-break-insert {location}"))
        bkpt = payload.get("bkpt", {})
        return {
            "number": bkpt.get("number"),
            "location": location,
            "function": bkpt.get("func"),
            "file": bkpt.get("file") or bkpt.get("fullname"),
            "line": bkpt.get("line"),
            "address": bkpt.get("addr"),
        }

    def pause(self) -> dict:
        self._mi("-exec-interrupt")
        self.halted = True
        return self.session_info()

    def cont(self) -> dict:
        self._mi("-exec-continue")
        self.halted = False
        return {"state": "running"}

    def step(self, kind: str = "over") -> dict:
        self._require_halted()
        mi_cmd = {"over": "-exec-next", "into": "-exec-step", "out": "-exec-finish"}.get(kind)
        if mi_cmd is None:
            raise DebugError(f"unknown step kind {kind!r} — use over | into | out")
        self._mi(mi_cmd)
        return self.session_info()

    def gdb_command(self, command: str) -> dict:
        command = command.strip()
        if command.startswith("-"):
            responses = self._mi(command)
            return {"command": command, "result": _result(responses)}
        responses = self._mi(f'-interpreter-exec console "{command}"')
        return {"command": command, "output": _console_text(responses)}


def _hex_dump(begin, contents: str) -> str:
    """Render a hex string as an offset-prefixed dump, 16 bytes per line."""
    try:
        base = int(str(begin), 16) if begin else 0
    except (TypeError, ValueError):
        base = 0
    out = []
    for i in range(0, len(contents), 32):  # 32 hex chars == 16 bytes
        row = contents[i:i + 32]
        pairs = " ".join(row[j:j + 2] for j in range(0, len(row), 2))
        out.append(f"0x{base + i // 2:08x}: {pairs}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_SESSION: Optional[DebugSession] = None


def get_session() -> Optional[DebugSession]:
    return _SESSION


def require_session() -> DebugSession:
    if _SESSION is None:
        raise DebugError("no active debug session — call debug_start first")
    return _SESSION


def start_session(
    elf: Optional[str] = None,
    board: Optional[str] = None,
    interface: Optional[str] = None,
) -> dict:
    """Create (or replace) the singleton debug session and return its session info."""
    global _SESSION
    if _SESSION is not None:
        _SESSION.stop()
        _SESSION = None
    openocd = find_openocd()
    if not openocd:
        raise DebugError(
            "OpenOCD not found — install it via PlatformIO "
            "(`pio pkg install -g -t platformio/tool-openocd-esp32`) or put `openocd` on PATH"
        )
    chip = detect_chip(board)
    gdb = find_gdb(chip)
    if not gdb:
        raise DebugError(
            f"GDB for {chip} not found — install the Espressif toolchain via PlatformIO "
            f"(build once for this board) or put the esp gdb on PATH"
        )
    elf_path = resolve_elf(elf)
    cfg_args = openocd_config(chip, interface)
    session = DebugSession(chip, elf_path, openocd, gdb, cfg_args)
    info = session.start()
    _SESSION = session
    return info


def stop_session() -> bool:
    """Tear down the singleton session. Returns True if one was active."""
    global _SESSION
    if _SESSION is None:
        return False
    _SESSION.stop()
    _SESSION = None
    return True
