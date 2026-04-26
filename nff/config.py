"""Read and write ~/.nff/config.json.
  ┌──────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────┐
  │          Symbol          │                                       Purpose                                        │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ CONFIG_PATH              │ ~/.nff/config.json — single source of truth for the path                             │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ load()                   │ Reads and parses the file; returns DEFAULT_CONFIG if it doesn't exist yet            │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ save(config)             │ Atomically writes a dict to disk, creating ~/.nff/ if missing                        │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ get_default_device()     │ Convenience getter — used throughout commands/ and MCP tools                         │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ set_default_device(...)  │ Convenience setter — called by nff init after port detection                         │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ get_wokwi_config()       │ Returns the wokwi block, merging with defaults for keys missing in older configs     │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ set_wokwi_token(token)   │ Persists the Wokwi CI API token; pass None to clear it                              │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ set_wokwi_diagram_path() │ Persists the path to a custom diagram.json; pass None to use auto-generation        │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ set_wokwi_timeout(ms)    │ Persists the default simulation timeout                                             │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ exists()                 │ Used by nff doctor to check if init has been run                                     │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
  │ ConfigError              │ Single exception type so callers don't catch both OSError and JSONDecodeError        │
  └──────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".nff"
CONFIG_PATH = CONFIG_DIR / "config.json"

_DEFAULT_WOKWI: dict[str, Any] = {
    "api_token": None,
    "default_timeout_ms": 5000,
    "diagram_path": None,
}

DEFAULT_CONFIG: dict[str, Any] = {
    "version": "1",
    "default_device": {
        "port": None,
        "board": None,
        "fqbn": None,
        "baud": 9600,
    },
    "wokwi": dict(_DEFAULT_WOKWI),
}


def load() -> dict[str, Any]:
    """Return the parsed config, or the default config if none exists."""
    if not CONFIG_PATH.exists():
        return _deep_copy_default()
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


def get_wokwi_config() -> dict[str, Any]:
    """Return the wokwi block, filling in defaults for any missing keys.

    Safe to call on configs written before Wokwi support was added.
    """
    stored = load().get("wokwi", {})
    return {**_DEFAULT_WOKWI, **stored}


def set_wokwi_token(token: str | None) -> None:
    """Persist the Wokwi CI API token. Pass None to clear it."""
    _update_wokwi({"api_token": token})


def set_wokwi_diagram_path(path: str | None) -> None:
    """Persist the path to a custom diagram.json. Pass None for auto-generation."""
    _update_wokwi({"diagram_path": path})


def set_wokwi_timeout(timeout_ms: int) -> None:
    """Persist the default simulation timeout in milliseconds."""
    _update_wokwi({"default_timeout_ms": timeout_ms})


def exists() -> bool:
    """Return True if the config file is present on disk."""
    return CONFIG_PATH.exists()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _update_wokwi(patch: dict[str, Any]) -> None:
    """Merge *patch* into the wokwi block and save."""
    config = load()
    wokwi = {**_DEFAULT_WOKWI, **config.get("wokwi", {}), **patch}
    config["wokwi"] = wokwi
    save(config)


def _deep_copy_default() -> dict[str, Any]:
    """Return a fresh copy of DEFAULT_CONFIG with no shared mutable state."""
    return json.loads(json.dumps(DEFAULT_CONFIG))


class ConfigError(RuntimeError):
    """Raised when the config file cannot be read or written."""
