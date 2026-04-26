"""Wokwi simulator integration — diagram generation, project setup, simulation run.

  ┌──────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────┐
  │                  Symbol                  │                                  Purpose                                 │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ FQBN_TO_CHIP                             │ Maps board FQBNs to Wokwi simulator chip IDs                             │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ generate_diagram(fqbn)                   │ Returns a minimal diagram.json dict for the given board                  │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ write_wokwi_toml(project_dir, elf_path)  │ Writes wokwi.toml pointing at the compiled ELF                           │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ _resolve_token()                         │ env WOKWI_CLI_TOKEN → config api_token → None                            │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ WokwiRunner                              │ Wraps wokwi-cli subprocess; .run() returns a WokwiResult                 │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ WokwiResult                              │ Dataclass returned by WokwiRunner.run()                                  │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ WokwiError                               │ Raised for missing CLI, unsupported board, or subprocess failure         │
  └──────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from nff.config import ConfigError, get_wokwi_config

# Maps board FQBNs to Wokwi simulator chip IDs.
# Only boards with confirmed Wokwi support are listed here.
FQBN_TO_CHIP: dict[str, str] = {
    "arduino:avr:uno":         "wokwi-arduino-uno",
    "arduino:avr:mega":        "wokwi-arduino-mega",
    "arduino:avr:nano":        "wokwi-arduino-nano",
    "arduino:avr:leonardo":    "wokwi-arduino-leonardo",
    "esp32:esp32:esp32":       "wokwi-esp32-devkit-v1",
    "esp8266:esp8266:generic": "wokwi-esp8266",
}


class WokwiError(RuntimeError):
    """Raised when a Wokwi operation cannot be completed.

    Common causes: wokwi-cli not installed, unsupported board FQBN,
    subprocess timeout, or missing API token.
    """


@dataclass
class WokwiResult:
    """Output from a single wokwi-cli simulation run."""

    serial_output: str
    exit_code: int
    simulated: bool = field(default=True, init=False)

    @property
    def success(self) -> bool:
        return self.exit_code == 0


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------

def _resolve_token() -> str | None:
    """Return the Wokwi CI API token, or None if not configured.

    Priority:
    1. ``WOKWI_CLI_TOKEN`` environment variable
    2. ``wokwi.api_token`` in ``~/.nff/config.json``
    3. ``None``
    """
    env_token = os.environ.get("WOKWI_CLI_TOKEN")
    if env_token:
        return env_token
    try:
        return get_wokwi_config().get("api_token") or None
    except ConfigError:
        return None


# ---------------------------------------------------------------------------
# Diagram generation
# ---------------------------------------------------------------------------

def generate_diagram(fqbn: str) -> dict:
    """Return a minimal Wokwi diagram.json dict for the given board FQBN.

    The diagram contains a single MCU component and no wiring. It is the
    starting point that Claude or the user can extend by adding components
    and connections.

    Args:
        fqbn: Fully-qualified board name, e.g. ``arduino:avr:uno``.

    Returns:
        A dict matching the Wokwi diagram.json schema.

    Raises:
        WokwiError: If the FQBN has no known Wokwi chip mapping.
    """
    chip = FQBN_TO_CHIP.get(fqbn)
    if chip is None:
        raise WokwiError(
            f"Unsupported board for Wokwi simulation: '{fqbn}'. "
            f"Supported FQBNs: {', '.join(sorted(FQBN_TO_CHIP))}"
        )
    part_id = fqbn.rsplit(":", 1)[-1] + "1"
    return {
        "version": 1,
        "author": "nff",
        "editor": "wokwi",
        "parts": [
            {
                "type": chip,
                "id": part_id,
                "top": 0,
                "left": 0,
                "attrs": {},
            }
        ],
        "connections": [],
    }


# ---------------------------------------------------------------------------
# wokwi.toml writer
# ---------------------------------------------------------------------------

def write_wokwi_toml(project_dir: Path, elf_path: Path) -> Path:
    """Write a ``wokwi.toml`` file into *project_dir* pointing at *elf_path*.

    Args:
        project_dir: Directory that will be passed to ``wokwi-cli run``.
        elf_path: Absolute path to the compiled ELF binary.

    Returns:
        Path to the written ``wokwi.toml``.
    """
    toml_content = (
        "[wokwi]\n"
        "version = 1\n"
        f'elf = "{elf_path.as_posix()}"\n'
        'firmware = ""\n'
    )
    toml_path = project_dir / "wokwi.toml"
    toml_path.write_text(toml_content, encoding="utf-8")
    return toml_path


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class WokwiRunner:
    """Wraps the ``wokwi-cli`` subprocess for simulation runs.

    Args:
        token: Wokwi CI API token. If not provided, resolved via
            :func:`_resolve_token` (env var → config → ``None``).
    """

    def __init__(self, token: str | None = None) -> None:
        self.token: str | None = token if token is not None else _resolve_token()

    def run(
        self,
        project_dir: Path,
        timeout_ms: int = 5000,
    ) -> WokwiResult:
        """Run the Wokwi simulator and return the result.

        Calls ``wokwi-cli run <project_dir> --timeout <timeout_ms>``.
        The project directory must already contain ``wokwi.toml`` and
        ``diagram.json`` before this method is called.

        The API token (if set) is injected via the ``WOKWI_CLI_TOKEN``
        environment variable rather than a CLI flag.

        Args:
            project_dir: Path to the Wokwi project directory.
            timeout_ms: Simulation wall-clock timeout in milliseconds.

        Returns:
            A :class:`WokwiResult` with captured serial output and exit code.

        Raises:
            WokwiError: If ``wokwi-cli`` is not installed, or if the
                subprocess times out at the OS level.
        """
        cmd = [
            "wokwi-cli", "run",
            str(project_dir),
            "--timeout", str(timeout_ms),
        ]

        # subprocess-level hard timeout adds headroom for CLI startup/shutdown.
        proc_timeout = timeout_ms / 1000 + 10

        run_kwargs: dict = {
            "capture_output": True,
            "text": True,
            "timeout": proc_timeout,
        }

        if self.token:
            env = os.environ.copy()
            env["WOKWI_CLI_TOKEN"] = self.token
            run_kwargs["env"] = env

        try:
            result = subprocess.run(cmd, **run_kwargs)
        except FileNotFoundError as exc:
            raise WokwiError(
                "wokwi-cli not found. "
                "Install it from https://github.com/wokwi/wokwi-cli "
                "and configure an API token with `nff wokwi init`."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise WokwiError(
                f"Simulation timed out after {proc_timeout:.0f}s "
                f"(wokwi timeout was {timeout_ms}ms)."
            ) from exc

        return WokwiResult(
            serial_output=result.stdout,
            exit_code=result.returncode,
        )