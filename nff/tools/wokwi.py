"""Wokwi circuit simulation — diagram generation and runner."""

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nff import config
from nff.tools import toolchain

FQBN_TO_CHIP: dict[str, str] = {
    "arduino:avr:uno":         "wokwi-arduino-uno",
    "arduino:avr:mega":        "wokwi-arduino-mega",
    "arduino:avr:nano":        "wokwi-arduino-nano",
    "arduino:avr:leonardo":    "wokwi-arduino-leonardo",
    "esp32:esp32:esp32":       "wokwi-esp32-devkit-v1",
    "esp8266:esp8266:generic": "wokwi-esp8266",
}


class WokwiError(Exception):
    pass


@dataclass
class WokwiResult:
    serial_output: str
    exit_code: int
    simulated: bool = field(default=True, init=False)

    @property
    def success(self) -> bool:
        return self.exit_code == 0


def _resolve_token() -> Optional[str]:
    token = os.environ.get("WOKWI_CLI_TOKEN")
    if token:
        return token
    return config.get_wokwi_config().get("api_token")


def generate_diagram(fqbn: str) -> dict:
    chip = FQBN_TO_CHIP.get(fqbn)
    if chip is None:
        raise WokwiError(f"Unsupported board FQBN: {fqbn}")
    return {
        "version": 1,
        "author": "nff",
        "editor": "wokwi",
        "parts": [{"id": "board", "type": chip, "top": 0, "left": 0, "attrs": {}}],
        "connections": [],
    }


def _rel(project_dir: Path, p: Path) -> str:
    try:
        rel = p.relative_to(project_dir)
    except ValueError:
        rel = p
    return str(rel).replace("\\", "/")


def write_wokwi_toml(project_dir: Path, elf_path: Path,
                     firmware_path: Optional[Path] = None) -> Path:
    """Write wokwi.toml. ``elf`` drives the simulator; ``firmware`` is the
    merged image for real hardware. If ``firmware_path`` is omitted we look for
    the sibling ``*.merged.bin`` so the field is correct instead of empty."""
    elf_str = _rel(project_dir, elf_path)
    if firmware_path is None:
        merged = elf_path.with_name(elf_path.name.replace(".ino.elf", ".ino.merged.bin"))
        if merged.exists():
            firmware_path = merged
    fw_str = _rel(project_dir, firmware_path) if firmware_path else ""
    toml_path = project_dir / "wokwi.toml"
    toml_path.write_text(
        f'[wokwi]\nversion = 1\nelf = "{elf_str}"\nfirmware = "{fw_str}"\n',
        encoding="utf-8",
    )
    return toml_path


_UNSET = object()


class WokwiRunner:
    def __init__(self, token=_UNSET) -> None:
        self.token = _resolve_token() if token is _UNSET else token

    def run(
        self,
        project_dir: Path,
        timeout_ms: int = 5000,
        elf: Optional[Path] = None,
    ) -> WokwiResult:
        cli = toolchain.find_wokwi_cli()
        cmd = [str(cli) if cli else "wokwi-cli", "run",
               "--timeout", str(timeout_ms), str(project_dir)]
        if elf is not None:
            cmd += ["--elf", str(elf)]

        extra: dict = {}
        if self.token:
            env = dict(os.environ)
            env["WOKWI_CLI_TOKEN"] = self.token
            extra["env"] = env

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                **extra,
            )
        except FileNotFoundError as exc:
            raise WokwiError(f"wokwi-cli not found: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise WokwiError(f"wokwi-cli timed out: {exc}") from exc

        return WokwiResult(
            serial_output=proc.stdout or "",
            exit_code=proc.returncode,
        )
