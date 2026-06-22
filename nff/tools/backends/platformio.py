"""PlatformIO build backend — board-universal compile/upload for nff.

Mirrors the arduino-cli functions in :mod:`nff.tools.toolchain` (``resolve_project``,
``stream_compile``/``stream_upload``, ``compile_sketch``/``upload_sketch``,
``discover_artifacts``) so ``toolchain`` can delegate to whichever backend is active.

Where the arduino backend keeps a ``.ino`` whose name matches its folder, PlatformIO
uses a project layout: a generated ``platformio.ini`` + ``src/main.cpp``. Because a
``.cpp`` gets none of the Arduino ``.ino`` preprocessing, we inject ``#include
<Arduino.h>`` when the source omits it. The nff SDK is materialised into the project's
``lib/`` (PlatformIO auto-compiles ``lib/*``), and external Arduino libraries are added
to ``lib_deps`` only when the source references them — so a bare blink sketch needs no
network beyond PlatformIO's one-time platform install.

The board identifier here is a PlatformIO board id (e.g. ``esp32dev``), not an
arduino-cli FQBN. The catalog in :mod:`nff.tools.boards` supplies the platform for the
common families; any board id is still accepted (PlatformIO resolves + installs the
platform on first build), which is what makes nff board-universal.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional

from nff.tools import boards as _boards
from nff.tools import retry as _retry
from nff.tools import toolchain as _tc

# PlatformIO scratch projects live here, one dir per sketch stem (deterministic so a
# resolve→compile→discover sequence keeps hitting the same .pio/build output).
_PIO_DIR = Path(_tc.tempfile.gettempdir()) / "nff_pio"

# The single PlatformIO environment name we generate. Compile/upload pin -e to it so
# the build dir is always .pio/build/<_ENV>/.
_ENV = "nff"

_DEFAULT_MONITOR_SPEED = 115200

# Sketch translation units + headers we copy into a scaffold's src/ for multi-file
# sketches. PlatformIO's arduino framework concatenates the .ino/.pde tabs and generates
# prototypes, exactly as arduino-cli does.
_SOURCE_EXTS = (".ino", ".pde", ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hh")

Emit = Callable[[str], None]


def _is_scaffolded(project_dir: Path) -> bool:
    """True if project_dir is an nff-generated scaffold under _PIO_DIR.

    A project that is *not* scaffolded was supplied by the user (a BYO PlatformIO
    project returned untouched by :func:`resolve_project`), so its ``platformio.ini``
    and env names are theirs to keep — nff must not overwrite or pin ``-e nff`` on it.
    """
    try:
        Path(project_dir).resolve().relative_to(_PIO_DIR.resolve())
        return True
    except (ValueError, OSError):
        return False


def _env_args(project_dir: Path) -> list[str]:
    """``-e nff`` for nff scaffolds; nothing for BYO projects (build their own envs)."""
    return ["-e", _ENV] if _is_scaffolded(project_dir) else []


# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------

def find_platformio() -> Optional[list[str]]:
    """Return a command prefix that runs PlatformIO, or None if unavailable.

    Tries ``pio``/``platformio`` on PATH, then PlatformIO's bundled penv, then
    ``python -m platformio`` as a last resort (pip-installed into the active env).
    """
    for exe in ("pio", "platformio"):
        found = shutil.which(exe)
        if found:
            return [found]

    penv = Path.home() / ".platformio" / "penv"
    sub = "Scripts" if sys.platform == "win32" else "bin"
    suffix = ".exe" if sys.platform == "win32" else ""
    for exe in ("pio", "platformio"):
        candidate = penv / sub / f"{exe}{suffix}"
        if candidate.exists():
            return [str(candidate)]

    try:
        import importlib.util
        if importlib.util.find_spec("platformio") is not None:
            return [sys.executable, "-m", "platformio"]
    except Exception:
        pass
    return None


def platformio_version() -> Optional[str]:
    cmd = find_platformio()
    if not cmd:
        return None
    return _tc._version_of([*cmd, "--version"])


def _require_pio() -> list[str]:
    cmd = find_platformio()
    if not cmd:
        raise _tc.ToolchainError("platformio not found — run `nff install-deps`")
    return cmd


# ---------------------------------------------------------------------------
# Project scaffolding
# ---------------------------------------------------------------------------

def _project_dir(source: Optional[Path], sketch_dir: Optional[Path]) -> Path:
    if sketch_dir is not None:
        return Path(sketch_dir)
    if source is not None:
        src = Path(source)
        stem = src.stem if src.is_file() else src.name
        return _PIO_DIR / stem
    return _PIO_DIR / "sketch"


def _read_source_code(code: Optional[str], source: Optional[Path]) -> str:
    if code is not None:
        return code
    if source is not None:
        src = Path(source)
        if src.is_dir():
            for pattern in ("*.ino", "src/*.cpp", "*.cpp"):
                hits = sorted(src.glob(pattern))
                if hits:
                    return hits[0].read_text(encoding="utf-8")
            raise _tc.ToolchainError(f"No .ino/.cpp source found in {src}")
        if src.is_file():
            return src.read_text(encoding="utf-8")
        raise _tc.ToolchainError(f"Not a sketch file or directory: {src}")
    raise _tc.ToolchainError(
        "provide either code= or source= (a .ino/.cpp file or sketch folder)"
    )


def _ensure_arduino_header(code: str) -> str:
    """A .cpp gets no implicit Arduino preprocessing, so guarantee Arduino.h."""
    if "Arduino.h" in code:
        return code
    return "#include <Arduino.h>\n" + code


def _copy_sketch_sources(src_dir: Path, project_dir: Path) -> list[str]:
    """Copy every translation unit + header from a sketch folder into project_dir/src.

    Handles multi-tab .ino sketches and helper .cpp/.h files: PlatformIO's arduino
    framework concatenates the .ino tabs and generates prototypes. Stale sources from a
    previous build of the same stem are wiped first (lib/ and .pio/ are preserved).
    """
    out = project_dir / "src"
    if out.exists():
        for p in out.iterdir():
            if p.is_file() and p.suffix.lower() in _SOURCE_EXTS:
                p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    search_dirs = [src_dir]
    nested = src_dir / "src"
    if nested.is_dir():
        search_dirs.append(nested)
    for d in search_dirs:
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in _SOURCE_EXTS:
                shutil.copy2(p, out / p.name)
                copied.append(p.name)
    if not copied:
        raise _tc.ToolchainError(f"No .ino/.cpp source found in {src_dir}")

    # A .cpp-only folder gets no implicit Arduino preprocessing, so guarantee Arduino.h
    # on its primary unit. .ino folders need nothing — PlatformIO injects it.
    if not any(name.lower().endswith((".ino", ".pde")) for name in copied):
        cpps = [n for n in copied if n.lower().endswith((".cpp", ".cc", ".cxx", ".c"))]
        if cpps:
            primary = (
                f"{src_dir.name}.cpp" if f"{src_dir.name}.cpp" in cpps
                else "main.cpp" if "main.cpp" in cpps
                else cpps[0]
            )
            target = out / primary
            target.write_text(
                _ensure_arduino_header(target.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
    return copied


def _combined_src_text(project_dir: Path) -> str:
    """All source text under project_dir/src, for library/SDK reference detection."""
    out = project_dir / "src"
    parts: list[str] = []
    if out.is_dir():
        for p in sorted(out.iterdir()):
            if p.is_file() and p.suffix.lower() in _SOURCE_EXTS:
                try:
                    parts.append(p.read_text(encoding="utf-8"))
                except OSError:
                    pass
    return "\n".join(parts)


def _materialize_nff_lib(project_dir: Path, code: str) -> None:
    """Drop the flat nff SDK into <project>/lib/nff when the sketch uses it.

    Best-effort: a sketch that does not ``#include <nff.h>`` needs nothing, and a
    materialisation failure (e.g. offline with no local checkout) must not abort the
    compile — the compiler error will be clear enough.
    """
    if "nff.h" not in code:
        return
    dest = project_dir / "lib" / "nff"
    if (dest / "library.properties").exists():
        return
    try:
        from nff.tools import arduino_lib
        arduino_lib.install_nff_library(dest=dest)
    except Exception:
        pass


def resolve_project(
    code: Optional[str] = None,
    source: Optional[Path] = None,
    sketch_dir: Optional[Path] = None,
) -> Path:
    """Return a ready-to-build PlatformIO project directory.

    A ``source`` directory that already contains a ``platformio.ini`` is used as-is.
    Otherwise a project is scaffolded under a deterministic temp dir: the sketch code
    is written to ``src/main.cpp`` (with ``#include <Arduino.h>`` ensured) and the nff
    SDK is materialised into ``lib/nff`` if referenced. ``platformio.ini`` itself is
    written later by :func:`stream_compile`/:func:`compile_sketch` once the board is
    known.
    """
    if source is not None:
        src = Path(source)
        if src.is_dir() and (src / "platformio.ini").exists():
            return src

    proj = _project_dir(source, sketch_dir)
    (proj / "src").mkdir(parents=True, exist_ok=True)
    if code is None and source is not None and Path(source).is_dir():
        # Multi-file sketch folder: copy every tab + helper, not just the first file.
        _copy_sketch_sources(Path(source), proj)
    else:
        main = _ensure_arduino_header(_read_source_code(code, source))
        (proj / "src" / "main.cpp").write_text(main, encoding="utf-8")
    _materialize_nff_lib(proj, _combined_src_text(proj))
    return proj


# ---------------------------------------------------------------------------
# platformio.ini generation
# ---------------------------------------------------------------------------

# Arduino libraries we know how to name in lib_deps, keyed by a token that appears in
# the sketch source when the library is used. The nff SDK is NOT here — it lives in
# lib/nff on the filesystem and is auto-discovered.
_LIB_DEPS = {
    "PubSubClient": "knolleary/PubSubClient",
}


def _lib_deps_for(code: str) -> list[str]:
    return [dep for token, dep in _LIB_DEPS.items() if token in code]


def _build_flags(board: str) -> str:
    # Keep the NFF_FQBN_TOKEN name so the firmware heartbeat reports board identity
    # exactly as it does under the arduino backend — just carrying the pio board id.
    return f"-DNFF_FQBN_TOKEN={board}"


def write_platformio_ini(project_dir: Path, board: str) -> Path:
    """Generate platformio.ini for ``board`` from the project's sources.

    A BYO project (one the user supplied, not an nff scaffold) keeps its own
    ``platformio.ini`` untouched — we never clobber custom partitions/PSRAM/build flags.
    """
    ini = project_dir / "platformio.ini"
    if not _is_scaffolded(project_dir) and ini.exists():
        return ini

    code = _combined_src_text(project_dir)
    platform = _boards.pio_platform_for(board)

    lines = [f"[env:{_ENV}]"]
    if platform:
        lines.append(f"platform = {platform}")
    lines.append(f"board = {board}")
    lines.append("framework = arduino")
    lines.append(f"monitor_speed = {_DEFAULT_MONITOR_SPEED}")
    lines.append(f"build_flags = {_build_flags(board)}")
    deps = _lib_deps_for(code)
    if deps:
        lines.append("lib_deps =")
        lines.extend(f"    {d}" for d in deps)

    ini.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ini


# ---------------------------------------------------------------------------
# Compile / upload
# ---------------------------------------------------------------------------

def _compile_cmd(project_dir: Path) -> list[str]:
    return [*_require_pio(), "run", *_env_args(project_dir), "-d", str(project_dir)]


def _upload_cmd(project_dir: Path, port: str) -> list[str]:
    cmd = [*_require_pio(), "run", *_env_args(project_dir),
           "-t", "upload", "-d", str(project_dir)]
    if port:
        cmd += ["--upload-port", port]
    return cmd


def _recover_packages(output: str, board: str, emit: Emit = print) -> None:
    """Best-effort repair of a half-installed PlatformIO platform between retries.

    A first build can leave a platform package corrupt (transient download/IO fault),
    which then surfaces as a missing pins_arduino.h. Pruning the broken platform makes
    the next ``pio run`` reinstall it clean. No-ops unless the output carries a package
    signature, and never raises — a failed prune must not turn a transient into a hard
    failure.
    """
    if not _retry._PIO_PACKAGE.search(output or ""):
        return
    platform = _boards.pio_platform_for(board)
    if not platform:
        return
    try:
        emit(f"[nff] repairing PlatformIO package '{platform}'…")
        _tc._run(
            [*_require_pio(), "pkg", "uninstall", "--global", "--platform", platform],
            timeout=300,
        )
    except Exception:
        pass


def compile_sketch(project_dir: Path, board: str) -> "_tc.RunResult":
    write_platformio_ini(project_dir, board)
    cmd = _compile_cmd(project_dir)
    return _retry.run_with_retry(
        lambda: _tc._run(cmd, timeout=_tc._COMPILE_TIMEOUT),
        recover=lambda out: _recover_packages(out, board),
    )


def upload_sketch(project_dir: Path, board: str, port: str) -> "_tc.RunResult":
    write_platformio_ini(project_dir, board)
    cmd = _upload_cmd(project_dir, port)
    return _retry.run_with_retry(
        lambda: _tc._run(cmd, timeout=_tc._UPLOAD_TIMEOUT),
        recover=lambda out: _recover_packages(out, board),
        backoff=(2.0, 4.0),
    )


def stream_compile(project_dir: Path, board: str) -> "_tc.ProcessStream":
    write_platformio_ini(project_dir, board)
    return _tc.ProcessStream(_compile_cmd(project_dir))


def stream_upload(project_dir: Path, board: str, port: str) -> "_tc.ProcessStream":
    write_platformio_ini(project_dir, board)
    return _tc.ProcessStream(_upload_cmd(project_dir, port))


# ---------------------------------------------------------------------------
# Artifact discovery
# ---------------------------------------------------------------------------

# kind → PlatformIO output filename under .pio/build/<env>/, in flash-priority order
# for the CompileResult "image" pick (merged_bin > bin > hex).
_PIO_ARTIFACTS = {
    "elf": "firmware.elf",
    "merged_bin": "firmware.merged.bin",
    "bin": "firmware.bin",
    "hex": "firmware.hex",
    "partitions_bin": "partitions.bin",
    "bootloader_bin": "bootloader.bin",
}


def _build_dir(project_dir: Path) -> Path:
    scaffold = project_dir / ".pio" / "build" / _ENV
    if scaffold.exists() or _is_scaffolded(project_dir):
        return scaffold
    # BYO project: the env name is the user's, not "nff" — pick the first build dir.
    builds = project_dir / ".pio" / "build"
    if builds.is_dir():
        subs = sorted(p for p in builds.iterdir() if p.is_dir())
        if subs:
            return subs[0]
    return scaffold


def discover_artifacts(project_dir: Path, board: str) -> dict[str, Path]:
    """Map artifact kind → absolute path for whatever PlatformIO produced."""
    build_dir = _build_dir(project_dir)
    found: dict[str, Path] = {}
    for kind, fname in _PIO_ARTIFACTS.items():
        candidate = build_dir / fname
        if candidate.exists():
            found[kind] = candidate
    # Fallbacks: a build layout we did not anticipate still resolves to something.
    if "elf" not in found:
        for p in build_dir.rglob("*.elf"):
            if p.is_file():
                found["elf"] = p
                break
    if not any(k in found for k in ("merged_bin", "bin", "hex")):
        for ext, kind in ((".merged.bin", "merged_bin"), (".bin", "bin"), (".hex", "hex")):
            for p in build_dir.rglob(f"*{ext}"):
                if p.is_file():
                    found[kind] = p
                    break
            if kind in found:
                break
    return found


# ---------------------------------------------------------------------------
# Toolchain install (mirrors installer.ensure_onboarding_toolchain for pio)
# ---------------------------------------------------------------------------

def install(emit: Emit = print) -> bool:
    """Install PlatformIO Core via pip into the active interpreter. Idempotent."""
    if find_platformio():
        return True
    emit("installing platformio…")
    result = _tc._run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "platformio"],
        timeout=600,
    )
    if not result.success:
        emit(result.output)
    return result.success


def ensure_toolchain(emit: Emit = print) -> tuple[bool, str]:
    """Ensure PlatformIO Core is present. Platforms/frameworks and external Arduino
    libraries self-install on the first ``pio run``, and the nff SDK is materialised
    per-project, so there is nothing else to pre-install here."""
    if not find_platformio():
        if not install(emit):
            return False, "could not install platformio"
    return True, "platformio ready"
