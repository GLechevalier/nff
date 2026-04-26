"""arduino-cli and esptool subprocess wrappers."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Iterator


_SKETCH_NAME = "nff_sketch"
# Fixed temp location so re-runs overwrite rather than accumulate.
_SKETCH_DIR = pathlib.Path(tempfile.gettempdir()) / _SKETCH_NAME


class ToolchainError(Exception):
    """Raised when a required tool is missing or a subprocess call fails to start."""


@dataclass
class RunResult:
    """Output from a single subprocess invocation."""

    success: bool
    stdout: str
    stderr: str
    returncode: int

    @property
    def output(self) -> str:
        """Concatenated stdout + stderr, whitespace-stripped."""
        parts = [p for p in (self.stdout.strip(), self.stderr.strip()) if p]
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------

def _arduino_cli_fallback_path() -> pathlib.Path | None:
    """Return the known installer location for arduino-cli, or None."""
    import os
    import platform
    if platform.system() == "Windows":
        base = pathlib.Path(
            os.environ.get("LOCALAPPDATA", pathlib.Path.home() / "AppData" / "Local")
        )
        candidate = base / "Programs" / "arduino-cli" / "arduino-cli.exe"
        return candidate if candidate.exists() else None
    candidate = pathlib.Path.home() / ".local" / "bin" / "arduino-cli"
    return candidate if candidate.exists() else None


def find_arduino_cli() -> str | None:
    """Return the absolute path to arduino-cli, or None if not found."""
    found = shutil.which("arduino-cli")
    if found:
        return found
    fallback = _arduino_cli_fallback_path()
    return str(fallback) if fallback else None


def find_esptool() -> str | None:
    """Return the absolute path to esptool / esptool.py, or None if not found."""
    return shutil.which("esptool.py") or shutil.which("esptool")


def find_wokwi_cli() -> str | None:
    """Return the absolute path to wokwi-cli, or None if not found."""
    return shutil.which("wokwi-cli")


def arduino_cli_version() -> str | None:
    """Return the arduino-cli version string, or None if not installed."""
    exe = find_arduino_cli()
    if exe is None:
        return None
    try:
        result = subprocess.run(
            [exe, "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or result.stderr.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def wokwi_cli_version() -> str | None:
    """Return the wokwi-cli version string, or None if not installed."""
    exe = find_wokwi_cli()
    if exe is None:
        return None
    try:
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or result.stderr.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def esptool_version() -> str | None:
    """Return the esptool version string, or None if not installed.

    Tries the standalone executable first, then falls back to
    ``python -m esptool`` for pip-installed variants.
    """
    exe = find_esptool()
    candidates: list[list[str]] = []
    if exe:
        candidates.append([exe, "version"])
    candidates.append([sys.executable, "-m", "esptool", "version"])

    for cmd in candidates:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip() or result.stderr.strip() or None
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


# ---------------------------------------------------------------------------
# Sketch management
# ---------------------------------------------------------------------------

def write_sketch(
    code: str,
    sketch_dir: pathlib.Path | None = None,
) -> pathlib.Path:
    """Write *code* to a .ino file ready for arduino-cli.

    arduino-cli requires the sketch file to live inside a directory whose
    name matches the file, e.g. ``nff_sketch/nff_sketch.ino``.

    Args:
        code: Full Arduino / C++ sketch source.
        sketch_dir: Target directory. Defaults to ``<tempdir>/nff_sketch/``.

    Returns:
        Path to the sketch directory (not the .ino file itself).
    """
    target = sketch_dir or _SKETCH_DIR
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{target.name}.ino").write_text(code, encoding="utf-8")
    return target


def elf_path_for(sketch_dir: pathlib.Path, fqbn: str) -> pathlib.Path:
    """Return the ELF output path that arduino-cli writes after compilation.

    arduino-cli places build artefacts under
    ``<sketch_dir>/build/<fqbn_with_dots>/<sketch_name>.elf``.
    Colons in the FQBN are replaced by dots to form a valid directory name.

    Args:
        sketch_dir: Root of the sketch directory (same value passed to
            :func:`write_sketch`).
        fqbn: Fully-qualified board name, e.g. ``arduino:avr:uno``.

    Returns:
        Absolute :class:`~pathlib.Path` to the expected ELF file.
        The file may not exist if compilation has not been run yet.
    """
    fqbn_dir = fqbn.replace(":", ".")
    return sketch_dir / "build" / fqbn_dir / f"{sketch_dir.name}.elf"


def compile(
    code: str,
    fqbn: str,
    sketch_dir: pathlib.Path | None = None,
) -> tuple[str, pathlib.Path]:
    """Write *code* to a sketch, compile it, and return the ELF path.

    Unlike :func:`flash`, this function does **not** upload to a device.
    It is the entry point for the Wokwi simulation flow:
    ``wokwi_flash`` calls this to obtain the compiled ELF binary, then
    passes it to ``WokwiRunner`` for simulation.

    Args:
        code: Full Arduino / C++ sketch source.
        fqbn: Fully-qualified board name, e.g. ``arduino:avr:uno``.
        sketch_dir: Override the default temp sketch directory.

    Returns:
        A ``(compile_output, elf_path)`` tuple where *compile_output* is the
        combined stdout/stderr from arduino-cli and *elf_path* is the absolute
        path to the compiled ELF file.

    Raises:
        ToolchainError: If arduino-cli is missing, fails to start, or the
            compilation exits with a non-zero code.
    """
    target_dir = write_sketch(code, sketch_dir)
    result = compile_sketch(target_dir, fqbn)
    if not result.success:
        raise ToolchainError(
            f"Compile failed (exit {result.returncode}):\n{result.output}"
        )
    return result.output, elf_path_for(target_dir, fqbn)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 120) -> RunResult:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return RunResult(
            success=proc.returncode == 0,
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
        )
    except FileNotFoundError as exc:
        raise ToolchainError(f"Executable not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolchainError(f"Command timed out after {timeout}s: {' '.join(cmd)}") from exc


class ProcessStream:
    """Iterable subprocess stream that records the exit code after iteration.

    Usage::

        stream = toolchain.stream_compile(sketch_dir, fqbn)
        for line in stream:
            print(line)
        if stream.returncode != 0:
            ...  # handle failure

    ``returncode`` is ``None`` until the for-loop (or manual ``__iter__``)
    is fully exhausted.
    """

    def __init__(self, cmd: list[str]) -> None:
        self._cmd = cmd
        self.returncode: int | None = None

    def __iter__(self) -> Iterator[str]:
        try:
            proc = subprocess.Popen(
                self._cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise ToolchainError(f"Executable not found: {self._cmd[0]}") from exc

        assert proc.stdout is not None
        for line in proc.stdout:
            yield line.rstrip("\n")
        proc.wait()
        self.returncode = proc.returncode


def _stream_process(cmd: list[str]) -> ProcessStream:
    """Return a :class:`ProcessStream` for *cmd*."""
    return ProcessStream(cmd)


def _require_arduino_cli() -> str:
    exe = find_arduino_cli()
    if exe is None:
        raise ToolchainError(
            "arduino-cli not found. "
            "Install it from https://arduino.github.io/arduino-cli"
        )
    return exe


# ---------------------------------------------------------------------------
# arduino-cli wrappers
# ---------------------------------------------------------------------------

def compile_sketch(sketch_dir: pathlib.Path, fqbn: str) -> RunResult:
    """Compile a sketch with arduino-cli.

    Args:
        sketch_dir: Path to the sketch directory (must contain a .ino file
            whose name matches the directory name).
        fqbn: Fully-qualified board name, e.g. ``arduino:avr:uno``.

    Returns:
        RunResult with compile stdout/stderr.

    Raises:
        ToolchainError: If arduino-cli is missing or fails to start.
    """
    exe = _require_arduino_cli()
    return _run([exe, "compile", "--fqbn", fqbn, str(sketch_dir)])


def upload_sketch(sketch_dir: pathlib.Path, fqbn: str, port: str) -> RunResult:
    """Upload a compiled sketch to a device with arduino-cli.

    Args:
        sketch_dir: Path to the sketch directory.
        fqbn: Fully-qualified board name.
        port: Serial port, e.g. ``COM3`` or ``/dev/ttyUSB0``.

    Returns:
        RunResult with upload stdout/stderr.

    Raises:
        ToolchainError: If arduino-cli is missing or fails to start.
    """
    exe = _require_arduino_cli()
    return _run([exe, "upload", "--fqbn", fqbn, "--port", port, str(sketch_dir)])


def stream_compile(sketch_dir: pathlib.Path, fqbn: str) -> ProcessStream:
    """Return a :class:`ProcessStream` for a compile run (for CLI display).

    Args:
        sketch_dir: Path to the sketch directory.
        fqbn: Fully-qualified board name.

    Returns:
        An iterable :class:`ProcessStream`; ``returncode`` is set after
        the iterator is exhausted.

    Raises:
        ToolchainError: If arduino-cli is missing or fails to start.
    """
    exe = _require_arduino_cli()
    return _stream_process([exe, "compile", "--fqbn", fqbn, str(sketch_dir)])


def stream_upload(sketch_dir: pathlib.Path, fqbn: str, port: str) -> ProcessStream:
    """Return a :class:`ProcessStream` for an upload run (for CLI display).

    Args:
        sketch_dir: Path to the sketch directory.
        fqbn: Fully-qualified board name.
        port: Serial port.

    Returns:
        An iterable :class:`ProcessStream`; ``returncode`` is set after
        the iterator is exhausted.

    Raises:
        ToolchainError: If arduino-cli is missing or fails to start.
    """
    exe = _require_arduino_cli()
    return _stream_process(
        [exe, "upload", "--fqbn", fqbn, "--port", port, str(sketch_dir)]
    )


# ---------------------------------------------------------------------------
# Combined flash (write + compile + upload) — called by the MCP tool
# ---------------------------------------------------------------------------

def flash(
    code: str,
    fqbn: str,
    port: str,
    sketch_dir: pathlib.Path | None = None,
) -> str:
    """Write *code* to a sketch, compile it, and upload it.

    This is the single function called by the ``flash`` MCP tool.
    All output is captured and returned as a human-readable string.

    Args:
        code: Full Arduino / C++ sketch source.
        fqbn: Fully-qualified board name, e.g. ``arduino:avr:uno``.
        port: Serial port, e.g. ``COM3`` or ``/dev/ttyUSB0``.
        sketch_dir: Override the default temp sketch directory.

    Returns:
        Starts with ``"OK:"`` on success or ``"ERROR:"`` on failure so
        MCP callers can detect outcome without exception handling.
    """
    try:
        target_dir = write_sketch(code, sketch_dir)
    except OSError as exc:
        return f"ERROR: Could not write sketch: {exc}"

    try:
        compile_result = compile_sketch(target_dir, fqbn)
    except ToolchainError as exc:
        return f"ERROR: {exc}"

    if not compile_result.success:
        return (
            f"ERROR: Compile failed (exit {compile_result.returncode}):\n"
            f"{compile_result.output}"
        )

    try:
        upload_result = upload_sketch(target_dir, fqbn, port)
    except ToolchainError as exc:
        return f"ERROR: {exc}"

    if not upload_result.success:
        return (
            f"ERROR: Upload failed (exit {upload_result.returncode}):\n"
            f"{upload_result.output}"
        )

    sections = ["OK: flash complete"]
    if compile_result.output:
        sections.append(f"--- compile ---\n{compile_result.output}")
    if upload_result.output:
        sections.append(f"--- upload ---\n{upload_result.output}")
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# esptool wrapper — raw binary flashing for ESP32 / ESP8266
# ---------------------------------------------------------------------------

def esptool_flash(
    port: str,
    bin_path: str | pathlib.Path,
    baud: int = 460800,
    address: str = "0x0",
) -> str:
    """Flash a binary image to an ESP board using esptool.

    Prefers the standalone ``esptool`` / ``esptool.py`` executable; falls
    back to ``python -m esptool`` for pip-installed setups.

    Args:
        port: Serial port, e.g. ``COM3`` or ``/dev/ttyUSB0``.
        bin_path: Path to the compiled ``.bin`` firmware file.
        baud: Upload baud rate (default 460800).
        address: Flash memory start address (default ``"0x0"``).

    Returns:
        Starts with ``"OK:"`` on success or ``"ERROR:"`` on failure.
    """
    exe = find_esptool()
    base_cmd: list[str] = [exe] if exe else [sys.executable, "-m", "esptool"]
    cmd = base_cmd + [
        "--port", port,
        "--baud", str(baud),
        "write_flash",
        address,
        str(bin_path),
    ]

    try:
        result = _run(cmd, timeout=120)
    except ToolchainError as exc:
        return f"ERROR: {exc}"

    if not result.success:
        return (
            f"ERROR: esptool failed (exit {result.returncode}):\n"
            f"{result.output}"
        )
    return f"OK: esptool flash complete\n{result.output}".strip()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== nff toolchain self-test ===")
    _acli = arduino_cli_version()
    print(f"arduino-cli : {_acli or 'NOT FOUND'}")
    _esp = esptool_version()
    print(f"esptool     : {_esp or 'NOT FOUND'}")
    _wokwi = wokwi_cli_version()
    print(f"wokwi-cli   : {_wokwi or 'NOT FOUND'}")
    print(f"sketch dir  : {_SKETCH_DIR}")
