import json

from core.config import clear_history, config_path, delete_history_records, get_api_key, load_config, load_history, save_config, save_history, set_api_key


def test_load_default_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))

    config = load_config()

    assert config.provider == "anthropic"
    assert config.conflict_policy == "ask"
    assert config.config_version == 1


def test_save_reload_and_migrate_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))
    (tmp_path / ".foldermind_config.json").write_text(json.dumps({"config_version": 0, "provider": "openai"}))

    config = load_config()
    config.theme = "light"
    save_config(config)
    loaded = load_config()
    raw = json.loads(config_path().read_text())

    assert loaded.provider == "openai"
    assert loaded.theme == "light"
    assert loaded.provider_endpoint_urls["openai"] == "https://api.openai.com/v1/chat/completions"
    assert loaded.conflict_policy == "ask"
    assert "api_key" not in str(raw).lower()


def test_config_persists_in_portable_config_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))

    config = load_config()
    config.provider = "custom"
    config.provider_endpoint_urls["custom"] = "https://api.example.com/v1/chat/completions"
    config.ai_timeout_seconds = 120
    config.ai_context_file_limit = 250
    save_config(config)

    assert config_path() == tmp_path / "config" / "config.json"
    loaded = load_config()
    assert loaded.provider_endpoint_urls["custom"] == "https://api.example.com/v1/chat/completions"
    assert loaded.ai_timeout_seconds == 120
    assert loaded.ai_context_file_limit == 250


def test_config_drops_invalid_provider_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))
    config_file = tmp_path / "config" / "config.json"
    config_file.parent.mkdir()
    config_file.write_text(json.dumps({
        "provider": "custom",
        "provider_models": {"custom": "ok", "": "bad"},
        "custom_models": {"custom": ["ok"], "乱码": ["bad"]},
        "provider_endpoint_urls": {"custom": "https://api.example.com", "": "bad"},
    }), encoding="utf-8")

    config = load_config()

    assert config.provider_models == {
        "anthropic": "claude-opus-4-6",
        "openai": "gpt-4o",
        "custom": "ok",
    }
    assert config.custom_models["custom"] == ["ok"]
    assert "" not in config.provider_endpoint_urls


def test_memory_api_key_round_trip():
    set_api_key("anthropic", "sk-test", memory_only=True)

    assert get_api_key("anthropic", memory_only=True) == "sk-test"


def test_history_persists_next_to_config(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))
    records = [{"id": "1", "workflowId": "w", "kind": "scan", "path": "x", "at": "now", "title": "x", "status": "success"}]

    save_history(records)

    assert load_history() == records
    assert (tmp_path / "history" / "history.json").exists()
    clear_history()
    assert load_history() == []


def test_history_loads_legacy_file_when_portable_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))
    records = [{"id": "legacy", "workflowId": "w", "kind": "scan", "path": "x", "at": "now", "title": "x", "status": "success"}]
    (tmp_path / ".foldermind_history.json").write_text(json.dumps(records), encoding="utf-8")

    assert load_history() == records


def test_history_save_merges_with_existing_records(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))
    old = {"id": "old", "workflowId": "w1", "kind": "scan", "path": "x", "at": "2026/5/17 10:00:00", "title": "old", "status": "success"}
    new = {"id": "new", "workflowId": "w2", "kind": "scan", "path": "y", "at": "2026/5/17 10:01:00", "title": "new", "status": "success"}
    save_history([old])

    save_history([new])

    ids = {record["id"] for record in load_history()}
    assert ids == {"old", "new"}


def test_empty_history_save_clears_existing_records(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))
    old = {"id": "old", "workflowId": "w1", "kind": "scan", "path": "x", "at": "2026/5/17 10:00:00", "title": "old", "status": "success"}
    save_history([old])

    save_history([])

    assert load_history() == []


def test_clear_history_removes_legacy_history_so_it_cannot_reappear(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))
    legacy = [{"id": "legacy", "workflowId": "w", "kind": "scan", "path": "x", "at": "now", "title": "legacy", "status": "success"}]
    portable = [{"id": "portable", "workflowId": "w", "kind": "scan", "path": "y", "at": "now", "title": "portable", "status": "success"}]
    (tmp_path / ".foldermind_history.json").write_text(json.dumps(legacy), encoding="utf-8")
    save_history(portable)

    clear_history()

    assert load_history() == []
    assert not (tmp_path / ".foldermind_history.json").exists()


def test_delete_history_records_removes_from_persistent_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))
    records = [
        {"id": "keep", "workflowId": "w1", "kind": "scan", "path": "x", "at": "2026/5/17 10:00:00", "title": "keep", "status": "success"},
        {"id": "delete", "workflowId": "w2", "kind": "scan", "path": "y", "at": "2026/5/17 10:01:00", "title": "delete", "status": "success"},
    ]
    save_history(records)

    assert delete_history_records(["delete"]) == 1

    loaded = load_history()
    assert [record["id"] for record in loaded] == ["keep"]
