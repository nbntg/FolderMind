import httpx

from core.api import cancel_ai_request, normalize_openai_compatible_endpoint, send_to_ai


def test_normalize_openai_compatible_endpoint_for_common_base_urls():
    assert normalize_openai_compatible_endpoint("https://api.siliconflow.cn") == "https://api.siliconflow.cn/v1/chat/completions"
    assert normalize_openai_compatible_endpoint("https://api.siliconflow.cn/v1") == "https://api.siliconflow.cn/v1/chat/completions"
    assert normalize_openai_compatible_endpoint("https://api.moonshot.ai/v1/chat/completions") == "https://api.moonshot.ai/v1/chat/completions"
    assert normalize_openai_compatible_endpoint("https://api.deepseek.com") == "https://api.deepseek.com/chat/completions"


def test_custom_404_error_mentions_actual_endpoint(monkeypatch):
    class Cfg:
        provider = "custom"
        provider_models = {"custom": "test-model"}
        provider_endpoint_urls = {"custom": "https://api.siliconflow.cn"}
        custom_endpoint_url = ""

    def fake_post(self, url, headers, json):
        request = httpx.Request("POST", url)
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    result = send_to_ai("hello", Cfg(), "sk-test")

    assert not result.ok
    assert "https://api.siliconflow.cn/v1/chat/completions" in result.error.message


def test_send_to_ai_uses_configured_timeout(monkeypatch):
    captured = {}

    class Cfg:
        provider = "custom"
        provider_models = {"custom": "test-model"}
        provider_endpoint_urls = {"custom": "https://api.example.com/v1/chat/completions"}
        custom_endpoint_url = ""
        ai_timeout_seconds = 12

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def post(self, url, headers, json):
            request = httpx.Request("POST", url)
            return httpx.Response(200, request=request, json={"choices": [{"message": {"content": "ok"}}]})

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(httpx, "Client", FakeClient)

    result = send_to_ai("hello", Cfg(), "sk-test")

    assert result.ok
    assert captured["timeout"] == 12
    assert captured["closed"]


def test_cancel_unknown_ai_request_returns_false():
    assert cancel_ai_request("missing-request") is False
