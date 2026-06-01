"""arduino-cli subprocess wrappers, sketch management, and flashing utilities."""

import io
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

_SKETCH_DIR = Path(tempfile.gettempdir()) / "nff_sketch"


class ToolchainError(Exception):
    pass


@dataclass
class RunResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int

    @property
    def output(self) -> str:
        parts = [s.strip() for s in (self.stdout, self.stderr) if s.strip()]
        return "\n".join(parts)


class ProcessStream:
    def __init__(self, cmd: list[str]) -> None:
        self._cmd = cmd
        self.returncode: Optional[int] = None

    def __iter__(self) -> Iterator[str]:
        try:
            proc = subprocess.Popen(
                self._cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            raise ToolchainError(f"Executable not found: {self._cmd[0]}")
        assert proc.stdout is not None
        for line in proc.stdout:
            yield line.rstrip("\n")
        proc.wait()
        self.returncode = proc.returncode


def _arduino_cli_fallback_path() -> Optional[str]:
    if sys.platform == "win32":
        import os
        base = os.environ.get("LOCALAPPDATA", "")
        candidate = Path(base) / "Programs" / "arduino-cli" / "arduino-cli.exe"
    else:
        candidate = Path.home() / ".local" / "bin" / "arduino-cli"
    return str(candidate) if candidate.exists() else None


def find_arduino_cli() -> Optional[str]:
    found = shutil.which("arduino-cli")
    if found:
        return found
    return _arduino_cli_fallback_path()


def find_esptool() -> Optional[str]:
    return shutil.which("esptool.py") or shutil.which("esptool")


def find_wokwi_cli() -> Optional[str]:
    found = shutil.which("wokwi-cli")
    if found:
        return found
    if sys.platform == "win32":
        import os
        base = os.environ.get("LOCALAPPDATA", "")
        candidate = Path(base) / "Programs" / "wokwi-cli" / "wokwi-cli.exe"
    else:
        candidate = Path.home() / ".local" / "bin" / "wokwi-cli"
    return str(candidate) if candidate.exists() else None


def _version_of(cmd: list[str]) -> Optional[str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return (r.stdout or r.stderr).strip().splitlines()[0]
    except Exception:
        pass
    return None


def arduino_cli_version() -> Optional[str]:
    cli = find_arduino_cli()
    if not cli:
        return None
    return _version_of([cli, "version"])


def esptool_version() -> Optional[str]:
    tool = find_esptool()
    if not tool:
        return None
    return _version_of([tool, "version"])


def wokwi_cli_version() -> Optional[str]:
    cli = find_wokwi_cli()
    if not cli:
        return None
    return _version_of([cli, "--version"])


def _require_arduino_cli() -> str:
    cli = find_arduino_cli()
    if not cli:
        raise ToolchainError("arduino-cli not found — run `nff install-deps`")
    return cli


def _run(cmd: list[str], timeout: int = 120) -> RunResult:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return RunResult(
            success=r.returncode == 0,
            stdout=r.stdout or "",
            stderr=r.stderr or "",
            returncode=r.returncode,
        )
    except FileNotFoundError:
        raise ToolchainError(f"Executable not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        raise ToolchainError(f"Command timed out: {cmd[0]}")


def write_sketch(code: str, sketch_dir: Optional[Path] = None) -> Path:
    if sketch_dir is None:
        sketch_dir = _SKETCH_DIR
    sketch_dir = Path(sketch_dir)
    sketch_dir.mkdir(parents=True, exist_ok=True)
    ino = sketch_dir / f"{sketch_dir.name}.ino"
    ino.write_text(code, encoding="utf-8")
    return sketch_dir


def elf_path_for(sketch_dir: Path, fqbn: str) -> Path:
    fqbn_dir = fqbn.replace(":", ".")
    sketch_name = sketch_dir.name
    return sketch_dir / "build" / fqbn_dir / f"{sketch_name}.ino.elf"


def locate_compiled_elf(sketch_dir: Path, fqbn: str) -> Path:
    expected = elf_path_for(sketch_dir, fqbn)
    if expected.exists():
        return expected
    # fallback: search recursively
    for p in sketch_dir.rglob("*.elf"):
        return p
    raise ToolchainError(f"Could not find compiled ELF in {sketch_dir}")


def compile_sketch(sketch_dir: Path, fqbn: str) -> RunResult:
    cli = _require_arduino_cli()
    build_path = sketch_dir / "build"
    build_path.mkdir(parents=True, exist_ok=True)
    return _run([cli, "compile", "--fqbn", fqbn,
                 "--build-path", str(build_path), str(sketch_dir)])


def upload_sketch(sketch_dir: Path, fqbn: str, port: str) -> RunResult:
    cli = _require_arduino_cli()
    return _run([cli, "upload", "--fqbn", fqbn, "--port", port, str(sketch_dir)])


def stream_compile(sketch_dir: Path, fqbn: str) -> ProcessStream:
    cli = _require_arduino_cli()
    build_path = sketch_dir / "build"
    build_path.mkdir(parents=True, exist_ok=True)
    return ProcessStream([cli, "compile", "--fqbn", fqbn,
                          "--build-path", str(build_path), str(sketch_dir)])


def stream_upload(sketch_dir: Path, fqbn: str, port: str) -> ProcessStream:
    cli = _require_arduino_cli()
    return ProcessStream([cli, "upload", "--fqbn", fqbn, "--port", port, str(sketch_dir)])


def compile(code: str, fqbn: str) -> tuple[str, Path]:
    sketch_dir = write_sketch(code)
    result = compile_sketch(sketch_dir, fqbn)
    elf = locate_compiled_elf(sketch_dir, fqbn) if result.success else Path("")
    return result.output, elf


def flash(code: str, fqbn: str, port: str, sketch_dir: Optional[Path] = None) -> str:
    try:
        sd = write_sketch(code, sketch_dir)
    except OSError as exc:
        return f"ERROR: {exc}"
    if not find_arduino_cli():
        return "ERROR: arduino-cli not found — run `nff install-deps`"
    compile_result = compile_sketch(sd, fqbn)
    if not compile_result.success:
        return f"ERROR: Compile failed:\n{compile_result.output}"
    upload_result = upload_sketch(sd, fqbn, port)
    if not upload_result.success:
        return f"ERROR: Upload failed:\n{upload_result.output}"
    return f"OK: flash complete\n--- compile ---\n{compile_result.output}\n--- upload ---\n{upload_result.output}"


def esptool_flash(port: str, bin_path: Path, baud: int = 921600, address: str = "0x0") -> str:
    tool = find_esptool()
    if not tool:
        return "ERROR: esptool not found — run `nff install-deps`"
    result = _run([tool, "--port", port, "--baud", str(baud),
                   "write_flash", address, str(bin_path)])
    if result.success:
        return f"OK: esptool flash complete\n{result.output}"
    return f"ERROR: {result.output}"
