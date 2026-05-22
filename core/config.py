from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, fields
from pathlib import Path

from .types import Config

_MEMORY_KEYS: dict[str, str] = {}


def config_path() -> Path:
    override = os.environ.get("FOLDERMIND_CONFIG")
    if override:
        return Path(override)
    return _portable_app_dir() / "config" / "config.json"


def legacy_config_path() -> Path:
    home = os.environ.get("FOLDERMIND_HOME") or os.environ.get("USERPROFILE") or os.environ.get("HOME") or str(Path.home())
    return Path(home) / ".foldermind_config.json"


def api_keys_path() -> Path:
    override = os.environ.get("FOLDERMIND_API_KEYS")
    if override:
        return Path(override)
    return _portable_app_dir() / "config" / "api_keys.json"


def history_path() -> Path:
    override = os.environ.get("FOLDERMIND_HISTORY")
    if override:
        return Path(override)
    base = _portable_app_dir()
    return base / "history" / "history.json"


def _portable_app_dir() -> Path:
    if os.environ.get("FOLDERMIND_HOME"):
        return Path(os.environ["FOLDERMIND_HOME"])
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def load_history() -> list[dict]:
    path = history_path()
    if not path.exists():
        legacy = legacy_config_path().with_name(".foldermind_history.json")
        if legacy.exists():
            return _read_history_file(legacy)
        return []
    return _read_history_file(path)


def _read_history_file(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else []


def save_history(records: list[dict]) -> None:
    path = history_path()
    if not records:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")
        legacy = legacy_config_path().with_name(".foldermind_history.json")
        if legacy.exists():
            legacy.unlink()
        return
    existing = load_history()
    by_id: dict[str, dict] = {}
    for record in existing:
        if isinstance(record, dict) and record.get("id"):
            by_id[str(record["id"])] = record
    for record in records:
        if isinstance(record, dict) and record.get("id"):
            by_id[str(record["id"])] = record
    merged = list(by_id.values())
    merged.sort(key=lambda item: item.get("at", ""), reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged[:200], ensure_ascii=False, indent=2), encoding="utf-8")


def delete_history_records(record_ids: list[str]) -> int:
    ids = {str(record_id) for record_id in record_ids if record_id}
    if not ids:
        return 0
    path = history_path()
    existing = load_history()
    remaining = [record for record in existing if str(record.get("id", "")) not in ids]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(remaining[:200], ensure_ascii=False, indent=2), encoding="utf-8")
    return len(existing) - len(remaining)


def clear_history() -> None:
    path = history_path()
    if path.exists():
        path.unlink()
    legacy = legacy_config_path().with_name(".foldermind_history.json")
    if legacy.exists():
        legacy.unlink()


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        legacy = legacy_config_path()
        if not legacy.exists():
            return Config()
        path = legacy
    raw = json.loads(path.read_text(encoding="utf-8"))
    allowed = {field.name for field in fields(Config)}
    values = {key: value for key, value in raw.items() if key in allowed}
    merged = asdict(Config())
    for key in ("provider_models", "provider_endpoint_urls", "custom_models"):
        if isinstance(values.get(key), dict):
            values[key] = {**merged[key], **_valid_provider_map(values[key])}
    if values.get("custom_endpoint_url") and "custom" not in values.get("provider_endpoint_urls", {}):
        values.setdefault("provider_endpoint_urls", merged["provider_endpoint_urls"])
        values["provider_endpoint_urls"]["custom"] = values["custom_endpoint_url"]
    merged.update(values)
    if merged.get("provider") not in {"anthropic", "openai", "custom"}:
        merged["provider"] = "anthropic"
    merged["config_version"] = 1
    return Config(**merged)


def _valid_provider_map(value: dict) -> dict:
    return {key: item for key, item in value.items() if key in {"anthropic", "openai", "custom"}}


def save_config(config: Config) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(config)
    data.pop("api_key", None)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def set_api_key(provider: str, api_key: str, memory_only: bool = False) -> None:
    if memory_only:
        _MEMORY_KEYS[provider] = api_key
        return
    try:
        import keyring
        keyring.set_password("FolderMind", provider, api_key)
    except Exception:
        _MEMORY_KEYS[provider] = api_key
        keys = _read_api_keys()
        keys[provider] = api_key
        _write_api_keys(keys)


def get_api_key(provider: str, memory_only: bool = False) -> str:
    if memory_only:
        return _MEMORY_KEYS.get(provider, "")
    try:
        import keyring
        return keyring.get_password("FolderMind", provider) or _MEMORY_KEYS.get(provider, "") or _read_api_keys().get(provider, "")
    except Exception:
        return _MEMORY_KEYS.get(provider, "") or _read_api_keys().get(provider, "")


def _read_api_keys() -> dict[str, str]:
    path = api_keys_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(key): str(value) for key, value in raw.items() if value}


def _write_api_keys(keys: dict[str, str]) -> None:
    path = api_keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keys, ensure_ascii=False, indent=2), encoding="utf-8")
