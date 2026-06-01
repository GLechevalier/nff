"""Config management for nff — reads/writes ~/.nff/config.json."""

import copy
import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".nff"
CONFIG_PATH = CONFIG_DIR / "config.json"

_DEFAULT = {
    "version": "1",
    "default_device": {"port": None, "board": None, "fqbn": None, "baud": 9600},
    "wokwi": {"api_token": None, "default_timeout_ms": 5000, "diagram_path": None},
    "diagnosis": {"server_url": "http://127.0.0.1:8080", "access_token": None, "refresh_token": None},
}


class ConfigError(Exception):
    pass


def load() -> dict:
    if not CONFIG_PATH.exists():
        return copy.deepcopy(_DEFAULT)
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ConfigError(f"Could not read {CONFIG_PATH}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read {CONFIG_PATH}: {exc}") from exc


def save(data: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2))
        os.replace(tmp, CONFIG_PATH)
    except OSError as exc:
        raise ConfigError(f"Could not write {CONFIG_PATH}: {exc}") from exc


def exists() -> bool:
    return CONFIG_PATH.exists()


def get_default_device() -> dict:
    try:
        return load().get("default_device", {})
    except ConfigError:
        return {}


def set_default_device(port, board, fqbn, baud: int = 9600) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("default_device", {})
    data["default_device"]["port"] = port
    data["default_device"]["board"] = board
    data["default_device"]["fqbn"] = fqbn
    data["default_device"]["baud"] = baud
    data.setdefault("version", "1")
    save(data)


def get_wokwi_config() -> dict:
    try:
        return load().get("wokwi", copy.deepcopy(_DEFAULT["wokwi"]))
    except ConfigError:
        return copy.deepcopy(_DEFAULT["wokwi"])


def set_wokwi_token(token) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("wokwi", copy.deepcopy(_DEFAULT["wokwi"]))
    data["wokwi"]["api_token"] = token
    save(data)


def set_wokwi_diagram_path(path) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("wokwi", copy.deepcopy(_DEFAULT["wokwi"]))
    data["wokwi"]["diagram_path"] = path
    save(data)


def set_wokwi_timeout(ms: int) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("wokwi", copy.deepcopy(_DEFAULT["wokwi"]))
    data["wokwi"]["default_timeout_ms"] = ms
    save(data)


def get_diagnosis_config() -> dict:
    try:
        return load().get("diagnosis", copy.deepcopy(_DEFAULT["diagnosis"]))
    except ConfigError:
        return copy.deepcopy(_DEFAULT["diagnosis"])


def set_diagnosis_tokens(access: str, refresh: str) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("diagnosis", copy.deepcopy(_DEFAULT["diagnosis"]))
    data["diagnosis"]["access_token"] = access
    data["diagnosis"]["refresh_token"] = refresh
    save(data)


def clear_diagnosis_tokens() -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("diagnosis", copy.deepcopy(_DEFAULT["diagnosis"]))
    data["diagnosis"]["access_token"] = None
    data["diagnosis"]["refresh_token"] = None
    save(data)


def set_diagnosis_server_url(url: str) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("diagnosis", copy.deepcopy(_DEFAULT["diagnosis"]))
    data["diagnosis"]["server_url"] = url
    save(data)
