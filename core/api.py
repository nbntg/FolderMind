from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from typing import Callable
from urllib.parse import urlparse, urlunparse

import httpx

from .types import ApiResult

DEFAULT_ENDPOINTS = {
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai": "https://api.openai.com/v1/chat/completions",
    "custom": "",
}
_REQUEST_CLIENTS: dict[str, httpx.Client] = {}
_REQUEST_LOCK = threading.Lock()


def send_to_ai(
    prompt: str,
    config,
    api_key: str,
    on_chunk: Callable[[str], None] | None = None,
    request_id: str = "",
) -> ApiResult[str]:
    if not api_key:
        return ApiResult.fail("API_KEY_MISSING", "请先在设置里填写 API Key。")

    provider = config.provider
    model = config.provider_models.get(provider, "")
    endpoint_url = _endpoint_for(config, provider)
    timeout_seconds = _timeout_for(config)
    try:
        if provider == "anthropic":
            return _anthropic(prompt, model, api_key, endpoint_url, on_chunk, request_id, timeout_seconds)
        return _openai_compatible(prompt, model, api_key, endpoint_url, provider, on_chunk, request_id, timeout_seconds)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        return ApiResult.fail("AI_REQUEST_FAILED", f"HTTP {status}: {_status_hint(status, provider, endpoint_url)}")
    except httpx.TimeoutException as exc:
        return ApiResult.fail(
            "AI_REQUEST_TIMEOUT",
            f"请求超时（{timeout_seconds} 秒）。当前服务商：{provider}，模型：{model or '未选择'}，接口：{endpoint_url}。原始错误：{exc}",
        )
    except httpx.RequestError as exc:
        return ApiResult.fail(
            "AI_REQUEST_FAILED",
            f"网络连接失败。当前服务商：{provider}，模型：{model or '未选择'}，接口：{endpoint_url}。原始错误：{exc}",
        )
    except Exception as exc:
        return ApiResult.fail("AI_REQUEST_FAILED", str(exc))


def test_connection(input_data: dict) -> ApiResult[dict]:
    provider = input_data.get("provider", "openai")

    class Cfg:
        provider_models = {key: input_data.get("model", "") for key in ["openai", "anthropic", "custom"]}
        provider_endpoint_urls = {
            "anthropic": input_data.get("anthropicUrl") or DEFAULT_ENDPOINTS["anthropic"],
            "openai": input_data.get("openaiUrl") or DEFAULT_ENDPOINTS["openai"],
            "custom": input_data.get("customUrl", ""),
        }
        custom_endpoint_url = provider_endpoint_urls["custom"]
        ai_timeout_seconds = input_data.get("timeoutSeconds", 60)

    Cfg.provider = provider
    start = time.perf_counter()
    result = send_to_ai("Reply with OK.", Cfg(), input_data.get("apiKey", ""), None)
    latency = int((time.perf_counter() - start) * 1000)
    if result.ok:
        return ApiResult.success({"success": True, "latencyMs": latency})
    return ApiResult.success({"success": False, "latencyMs": latency, "errorMessage": result.error.message if result.error else "失败"})


def cancel_ai_request(request_id: str) -> bool:
    if not request_id:
        return False
    with _REQUEST_LOCK:
        client = _REQUEST_CLIENTS.pop(request_id, None)
    if not client:
        return False
    try:
        client.close()
        return True
    except Exception:
        return False


def _endpoint_for(config, provider: str) -> str:
    endpoint_urls = getattr(config, "provider_endpoint_urls", {}) or {}
    endpoint = endpoint_urls.get(provider) or ""
    if not endpoint and provider == "custom":
        endpoint = getattr(config, "custom_endpoint_url", "") or ""
    endpoint = endpoint or DEFAULT_ENDPOINTS.get(provider, "")
    if provider == "custom":
        return normalize_openai_compatible_endpoint(endpoint)
    return endpoint


def _timeout_for(config) -> int:
    try:
        value = int(getattr(config, "ai_timeout_seconds", 60) or 60)
    except (TypeError, ValueError):
        value = 60
    return max(5, min(value, 300))


def normalize_openai_compatible_endpoint(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value

    path = parsed.path.rstrip("/")
    lower_path = path.lower()
    if lower_path.endswith("/chat/completions") or lower_path.endswith("/messages"):
        return value.rstrip("/")
    if lower_path.endswith("/v1"):
        return _replace_path(parsed, f"{path}/chat/completions")
    if lower_path in {"", "/"}:
        host = parsed.netloc.lower()
        if "deepseek.com" in host:
            return _replace_path(parsed, "/chat/completions")
        return _replace_path(parsed, "/v1/chat/completions")
    return value.rstrip("/")


def _replace_path(parsed, path: str) -> str:
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _status_hint(status: int, provider: str, endpoint_url: str) -> str:
    if status == 401:
        return "API Key 无效或没有权限。"
    if status == 403:
        return "服务拒绝访问，请检查 API Key、账户额度或模型权限。"
    if status == 404:
        if provider == "custom":
            return f"接口地址不存在。当前实际请求地址是 {endpoint_url}，第三方 OpenAI 兼容接口通常需要完整的 /chat/completions 路径。"
        return f"接口地址不存在：{endpoint_url}"
    if status == 429:
        return "请求过于频繁或额度不足。"
    return "服务返回错误，请检查模型名、接口地址和账户状态。"


def _openai_compatible(
    prompt: str,
    model: str,
    api_key: str,
    endpoint_url: str,
    provider: str,
    on_chunk,
    request_id: str = "",
    timeout_seconds: int = 60,
) -> ApiResult[str]:
    if not endpoint_url:
        return ApiResult.fail("CUSTOM_ENDPOINT_MISSING", "请先填写自定义 API 地址。")
    payload = {
        "model": model or ("gpt-4o" if provider == "openai" else ""),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    if on_chunk:
        return _stream_openai_compatible(request_id, endpoint_url, headers, payload, timeout_seconds, on_chunk)
    response = _post_json(request_id, endpoint_url, headers, payload, timeout_seconds)
    body = response.json()
    text = body.get("content") or body.get("choices", [{}])[0].get("message", {}).get("content") or json.dumps(body, ensure_ascii=False)
    if on_chunk:
        on_chunk(text)
    return ApiResult.success(text)


def _stream_openai_compatible(request_id: str, url: str, headers: dict, payload: dict, timeout_seconds: int, on_chunk) -> ApiResult[str]:
    stream_payload = {**payload, "stream": True}
    client = httpx.Client(timeout=httpx.Timeout(timeout_seconds, read=timeout_seconds))
    if request_id:
        with _REQUEST_LOCK:
            _REQUEST_CLIENTS[request_id] = client
    chunks: list[str] = []
    try:
        with client.stream("POST", url, headers=headers, json=stream_payload) as response:
            response.raise_for_status()
            for text in _iter_openai_stream_text(response.iter_lines()):
                chunks.append(text)
                on_chunk(text)
    finally:
        if request_id:
            with _REQUEST_LOCK:
                _REQUEST_CLIENTS.pop(request_id, None)
        client.close()
    return ApiResult.success("".join(chunks))


def _iter_openai_stream_text(lines: Iterator[str]) -> Iterator[str]:
    for line in lines:
        value = line.strip()
        if not value:
            continue
        if value.startswith("data:"):
            value = value[5:].strip()
        if value == "[DONE]":
            break
        try:
            event = json.loads(value)
        except json.JSONDecodeError:
            continue
        choice = (event.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        text = delta.get("content")
        if text is None:
            text = choice.get("message", {}).get("content")
        if text:
            yield text


def _anthropic(prompt: str, model: str, api_key: str, endpoint_url: str, on_chunk, request_id: str = "", timeout_seconds: int = 60) -> ApiResult[str]:
    payload = {"model": model or "claude-opus-4-6", "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]}
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    response = _post_json(request_id, endpoint_url or DEFAULT_ENDPOINTS["anthropic"], headers, payload, timeout_seconds)
    text = "".join(part.get("text", "") for part in response.json().get("content", []))
    if on_chunk:
        on_chunk(text)
    return ApiResult.success(text)


def _post_json(request_id: str, url: str, headers: dict, payload: dict, timeout_seconds: int = 60) -> httpx.Response:
    client = httpx.Client(timeout=timeout_seconds)
    if request_id:
        with _REQUEST_LOCK:
            _REQUEST_CLIENTS[request_id] = client
    try:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response
    finally:
        if request_id:
            with _REQUEST_LOCK:
                _REQUEST_CLIENTS.pop(request_id, None)
        client.close()
