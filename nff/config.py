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
    "diagnosis": {"server_url": "https://nanoforgeflow.com", "frontend_url": "https://nanoforgeflow.com", "access_token": None, "refresh_token": None},
    # Opaque tokens the local MCP OAuth proxy issues to Claude Code. Decoupled from
    # the diagnosis (Supabase) JWT so the MCP session does not expire with it.
    "mcp": {"access_token": None, "refresh_token": None},
    # Cloud agent pairing (`nff agent`). server_url = the deployed nff-agent-worker
    # HTTP endpoint; local_mcp_url = THIS bench's `nff mcp` (so the cloud agent can
    # reach the connected hardware); project_id is optional (the worker resolves it
    # from the diagnosis JWT when unset). Auth reuses the diagnosis tokens.
    "agent": {"server_url": "https://agent.nanoforgeflow.com", "local_mcp_url": "http://127.0.0.1:3010/mcp", "project_id": None},
    # Platform onboarding (`nff init` → connect a real board to the cloud fleet).
    # broker_host is the public mTLS broker the device dials; project_id/batch_id are
    # remembered so a re-run reuses the same project + bootstrap batch.
    "platform": {"broker_host": "152.228.219.243", "project_id": None, "batch_id": None},
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


def get_mcp_tokens() -> dict:
    try:
        return load().get("mcp", copy.deepcopy(_DEFAULT["mcp"]))
    except ConfigError:
        return copy.deepcopy(_DEFAULT["mcp"])


def set_mcp_tokens(access: str, refresh: str) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("mcp", copy.deepcopy(_DEFAULT["mcp"]))
    data["mcp"]["access_token"] = access
    data["mcp"]["refresh_token"] = refresh
    save(data)


def clear_mcp_tokens() -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("mcp", copy.deepcopy(_DEFAULT["mcp"]))
    data["mcp"]["access_token"] = None
    data["mcp"]["refresh_token"] = None
    save(data)


def set_diagnosis_server_url(url: str) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("diagnosis", copy.deepcopy(_DEFAULT["diagnosis"]))
    data["diagnosis"]["server_url"] = url
    save(data)


def get_agent_config() -> dict:
    """Cloud-agent pairing config, merged over defaults so older config files
    (written before this section existed) still return every key."""
    try:
        cfg = copy.deepcopy(_DEFAULT["agent"])
        cfg.update(load().get("agent", {}))
        return cfg
    except ConfigError:
        return copy.deepcopy(_DEFAULT["agent"])


def set_agent_server_url(url: str) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("agent", copy.deepcopy(_DEFAULT["agent"]))
    data["agent"]["server_url"] = url
    save(data)


def set_agent_local_mcp_url(url: str) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("agent", copy.deepcopy(_DEFAULT["agent"]))
    data["agent"]["local_mcp_url"] = url
    save(data)


def set_agent_project_id(project_id) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("agent", copy.deepcopy(_DEFAULT["agent"]))
    data["agent"]["project_id"] = project_id
    save(data)


def get_platform_config() -> dict:
    """Platform onboarding config, merged over defaults so older config files still
    return every key (broker_host in particular)."""
    try:
        cfg = copy.deepcopy(_DEFAULT["platform"])
        cfg.update(load().get("platform", {}))
        return cfg
    except ConfigError:
        return copy.deepcopy(_DEFAULT["platform"])


def set_platform_enrollment(project_id, batch_id) -> None:
    data = load() if exists() else copy.deepcopy(_DEFAULT)
    data.setdefault("platform", copy.deepcopy(_DEFAULT["platform"]))
    data["platform"]["project_id"] = project_id
    data["platform"]["batch_id"] = batch_id
    save(data)
