"""Read and write ~/.nff/config.json.
  ┌─────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────┐                
  │         Symbol          │                                        Purpose                                        │
  ├─────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤                
  │ CONFIG_PATH             │ ~/.nff/config.json — single source of truth for the path                              │              
  ├─────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ load()                  │ Reads and parses the file; returns DEFAULT_CONFIG if it doesn't exist yet             │
  ├─────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ save(config)            │ Atomically writes a dict to disk, creating ~/.nff/ if missing                         │
  ├─────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ get_default_device()    │ Convenience getter — used throughout commands/ and MCP tools                          │
  ├─────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ set_default_device(...) │ Convenience setter — called by nff init after port detection                          │
  ├─────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ exists()                │ Used by nff doctor to check if init has been run                                      │
  ├─────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ ConfigError             │ Single exception type so callers don't have to catch both OSError and JSONDecodeError │
  └─────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".nff"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "version": "1",
    "default_device": {
        "port": None,
        "board": None,
        "fqbn": None,
        "baud": 9600,
    },
}


def load() -> dict[str, Any]:
    """Return the parsed config, or the default config if none exists."""
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    try:
        with CONFIG_PATH.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError(f"Could not read {CONFIG_PATH}: {exc}") from exc


def save(config: dict[str, Any]) -> None:
    """Write *config* to disk, creating the directory if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with CONFIG_PATH.open("w") as f:
            json.dump(config, f, indent=2)
    except OSError as exc:
        raise ConfigError(f"Could not write {CONFIG_PATH}: {exc}") from exc


def get_default_device() -> dict[str, Any]:
    """Return the default_device block from the config."""
    return load().get("default_device", {})


def set_default_device(
    port: str,
    board: str,
    fqbn: str,
    baud: int = 9600,
) -> None:
    """Overwrite the default_device block and persist the config."""
    config = load()
    config["default_device"] = {
        "port": port,
        "board": board,
        "fqbn": fqbn,
        "baud": baud,
    }
    save(config)


def exists() -> bool:
    """Return True if the config file is present on disk."""
    return CONFIG_PATH.exists()


class ConfigError(RuntimeError):
    """Raised when the config file cannot be read or written."""
