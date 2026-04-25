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

def find_arduino_cli() -> str | None:
    """Return the absolute path to arduino-cli, or None if not in PATH."""
    return shutil.which("arduino-cli")


def find_esptool() -> str | None:
    """Return the absolute path to esptool / esptool.py, or None if not found."""
    return shutil.which("esptool.py") or shutil.which("esptool")


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


def _stream_process(cmd: list[str]) -> Iterator[str]:
    """Run *cmd* and yield stdout+stderr lines as they arrive."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise ToolchainError(f"Executable not found: {cmd[0]}") from exc

    assert proc.stdout is not None
    for line in proc.stdout:
        yield line.rstrip("\n")
    proc.wait()


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


def stream_compile(sketch_dir: pathlib.Path, fqbn: str) -> Iterator[str]:
    """Yield compile output lines in real time (for CLI display).

    Args:
        sketch_dir: Path to the sketch directory.
        fqbn: Fully-qualified board name.

    Yields:
        Output lines (stdout and stderr merged, as they arrive).

    Raises:
        ToolchainError: If arduino-cli is missing or fails to start.
    """
    exe = _require_arduino_cli()
    yield from _stream_process([exe, "compile", "--fqbn", fqbn, str(sketch_dir)])


def stream_upload(sketch_dir: pathlib.Path, fqbn: str, port: str) -> Iterator[str]:
    """Yield upload output lines in real time (for CLI display).

    Args:
        sketch_dir: Path to the sketch directory.
        fqbn: Fully-qualified board name.
        port: Serial port.

    Yields:
        Output lines.

    Raises:
        ToolchainError: If arduino-cli is missing or fails to start.
    """
    exe = _require_arduino_cli()
    yield from _stream_process(
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
    print(f"sketch dir  : {_SKETCH_DIR}")
