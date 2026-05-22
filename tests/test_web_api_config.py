from core.web_api import Api
import time


def test_web_api_save_config_keeps_custom_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLDERMIND_HOME", str(tmp_path))
    api = Api()
    config = api.load_config()["data"]
    config["provider"] = "custom"
    config["provider_endpoint_urls"]["custom"] = "https://api.siliconflow.cn"
    config["provider_models"]["custom"] = "Qwen/Qwen2.5-7B-Instruct"
    config["custom_models"]["custom"] = ["Qwen/Qwen2.5-7B-Instruct"]
    config["api_keys"] = {"custom": "sk-test"}

    assert api.save_config(config)["ok"]
    loaded = api.load_config()["data"]

    assert loaded["provider"] == "custom"
    assert loaded["provider_endpoint_urls"]["custom"] == "https://api.siliconflow.cn"
    assert loaded["custom_endpoint_url"] == "https://api.siliconflow.cn"
    assert loaded["provider_models"]["custom"] == "Qwen/Qwen2.5-7B-Instruct"
    assert loaded["api_keys"]["custom"] == "sk-test"


def test_generate_plan_uses_runtime_timeout_override(monkeypatch):
    captured = {}
    api = Api()

    def fake_send_to_ai(prompt, config, api_key, request_id=""):
        captured["timeout"] = config.ai_timeout_seconds
        captured["provider"] = config.provider
        captured["model"] = config.provider_models[config.provider]
        captured["request_id"] = request_id

        class Result:
            def to_dict(self):
                return {"ok": True, "data": "ok"}

        return Result()

    monkeypatch.setattr("core.web_api.send_to_ai", fake_send_to_ai)
    monkeypatch.setattr("core.web_api.get_api_key", lambda provider: "sk-test")

    response = api.generate_plan({
        "provider": "custom",
        "model": "third-party-model",
        "timeoutSeconds": 30,
        "requestId": "req-1",
        "userInstruction": "hello",
        "fileListForAi": "",
    })

    assert response["ok"]
    assert captured == {
        "timeout": 30,
        "provider": "custom",
        "model": "third-party-model",
        "request_id": "req-1",
    }


def test_cancel_ai_request_marks_stream_cancelled(monkeypatch):
    api = Api()
    api.ai_streams["req-1"] = {"content": "partial", "done": False, "error": None}
    monkeypatch.setattr("core.web_api.cancel_ai_request", lambda request_id: True)

    response = api.cancel_ai_request("req-1")
    poll = api.poll_ai_stream("req-1")

    assert response["ok"]
    assert response["data"]["cancelled"]
    assert poll["ok"]
    assert poll["data"]["content"] == "partial"
    assert poll["data"]["done"] is True
    assert poll["data"]["cancelled"] is True


def test_scan_job_progress_and_cancel(monkeypatch):
    api = Api()
    progress_callbacks = {}

    def fake_scan(path, exclude_rules, progress_callback=None, should_cancel=None):
        progress_callbacks["progress"] = progress_callback
        progress_callbacks["cancel"] = should_cancel
        if progress_callback:
            progress_callback(25, "file-25.txt")
        while not should_cancel():
            pass
        from core.scanner import ScanCancelled
        raise ScanCancelled()

    monkeypatch.setattr("core.web_api.fast_scan", fake_scan)

    started = api.start_scan("C:/big")
    job_id = started["data"]["jobId"]
    before_cancel = api.poll_scan(job_id)
    deadline = time.time() + 1
    while before_cancel["data"]["count"] == 0 and time.time() < deadline:
        before_cancel = api.poll_scan(job_id)
    cancelled = api.cancel_scan(job_id)

    assert before_cancel["data"]["count"] == 25
    assert before_cancel["data"]["done"] is False
    assert cancelled["ok"]
    assert api.poll_scan(job_id)["data"]["cancelled"] is True


def test_web_api_undo_clears_last_execute_after_restore(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    api = Api()
    plan = {
        "actions": [
            {"id": 1, "type": "create_dir", "path": "dest"},
            {"id": 2, "type": "move", "from": "a.txt", "to": "dest/a.txt"},
        ]
    }

    execute = api.execute_plan(str(tmp_path), plan, "auto_rename")
    undo = api.undo_last()
    second_undo = api.undo_last()

    assert execute["ok"]
    assert execute["data"]["undo_available"]
    assert undo["ok"]
    assert (tmp_path / "a.txt").exists()
    assert not (tmp_path / "dest").exists()
    assert not second_undo["ok"]
    assert second_undo["error"]["code"] == "UNDO_NOT_AVAILABLE"
