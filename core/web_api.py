from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

import webview

from .api import cancel_ai_request, send_to_ai, test_connection
from .config import clear_history, delete_history_records, get_api_key, history_path, load_config, load_history, save_config, save_history, set_api_key
from .executor import execute_plan, parse_json, preview_actions, undo_plan
from .prompts import delete_prompt, list_prompts, save_prompt
from .scanner import ScanCancelled, fast_scan, smart_output
from .types import ApiResult, Config, ExecuteResult, Plan, to_jsonable


class Api:
    def __init__(self):
        self.last_execute: ExecuteResult | None = None
        self.last_scan = None
        self.ai_streams: dict[str, dict] = {}
        self.ai_stream_lock = threading.Lock()
        self.scan_jobs: dict[str, dict] = {}
        self.scan_job_lock = threading.Lock()

    def scan_folder(self, path: str) -> dict:
        try:
            config = load_config()
            self.last_scan = fast_scan(path, config.exclude_rules)
            return ApiResult.success(self.last_scan).to_dict()
        except Exception as exc:
            return ApiResult.fail("SCAN_FAILED", str(exc)).to_dict()

    def start_scan(self, path: str) -> dict:
        job_id = uuid.uuid4().hex
        with self.scan_job_lock:
            self.scan_jobs[job_id] = {
                "jobId": job_id,
                "path": path,
                "count": 0,
                "currentPath": "",
                "done": False,
                "cancelled": False,
                "error": None,
                "result": None,
                "startedAt": time.time(),
            }

        def progress(count: int, current_path: str = "") -> None:
            with self.scan_job_lock:
                job = self.scan_jobs.get(job_id)
                if job:
                    job["count"] = count
                    job["currentPath"] = current_path

        def should_cancel() -> bool:
            with self.scan_job_lock:
                return bool(self.scan_jobs.get(job_id, {}).get("cancelled"))

        def worker() -> None:
            try:
                config = load_config()
                result = fast_scan(path, config.exclude_rules, progress_callback=progress, should_cancel=should_cancel)
                self.last_scan = result
                with self.scan_job_lock:
                    job = self.scan_jobs.get(job_id)
                    if job:
                        job["count"] = result.file_count
                        job["done"] = True
                        job["result"] = to_jsonable(result)
            except ScanCancelled:
                with self.scan_job_lock:
                    job = self.scan_jobs.get(job_id)
                    if job:
                        job["done"] = True
                        job["cancelled"] = True
            except Exception as exc:
                with self.scan_job_lock:
                    job = self.scan_jobs.get(job_id)
                    if job:
                        job["done"] = True
                        job["error"] = str(exc)

        threading.Thread(target=worker, daemon=True).start()
        return ApiResult.success({"jobId": job_id}).to_dict()

    def poll_scan(self, job_id: str) -> dict:
        with self.scan_job_lock:
            job = self.scan_jobs.get(job_id)
            if not job:
                return ApiResult.fail("SCAN_JOB_NOT_FOUND", "Scan job not found.").to_dict()
            data = dict(job)
            if data.get("done"):
                self.scan_jobs.pop(job_id, None)
        if data.get("error"):
            return ApiResult.fail("SCAN_FAILED", data["error"], data).to_dict()
        return ApiResult.success(data).to_dict()

    def cancel_scan(self, job_id: str) -> dict:
        with self.scan_job_lock:
            job = self.scan_jobs.get(job_id)
            if not job:
                return ApiResult.success({"cancelled": False}).to_dict()
            job["cancelled"] = True
        return ApiResult.success({"cancelled": True}).to_dict()

    def choose_folder(self) -> dict:
        try:
            window = webview.windows[0] if webview.windows else None
            if window is None:
                return ApiResult.fail("WINDOW_NOT_READY", "Window is not ready.").to_dict()
            result = window.create_file_dialog(webview.FOLDER_DIALOG)
            if not result:
                return ApiResult.fail("CANCELLED", "Folder selection cancelled.").to_dict()
            return ApiResult.success(result[0]).to_dict()
        except Exception as exc:
            return ApiResult.fail("CHOOSE_FOLDER_FAILED", str(exc)).to_dict()

    def choose_json_file(self) -> dict:
        try:
            window = webview.windows[0] if webview.windows else None
            if window is None:
                return ApiResult.fail("WINDOW_NOT_READY", "Window is not ready.").to_dict()
            result = window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("JSON or text files (*.json;*.txt)", "All files (*.*)"),
            )
            if not result:
                return ApiResult.fail("CANCELLED", "JSON selection cancelled.").to_dict()
            path = Path(result[0])
            return ApiResult.success({"path": str(path), "text": path.read_text(encoding="utf-8-sig")}).to_dict()
        except Exception as exc:
            return ApiResult.fail("CHOOSE_JSON_FAILED", str(exc)).to_dict()

    def read_text_file(self, path: str) -> dict:
        try:
            target = Path(path).resolve()
            if target.suffix.lower() not in {".json", ".txt"}:
                return ApiResult.fail("UNSUPPORTED_FILE_TYPE", "Only .json and .txt files can be imported here.").to_dict()
            return ApiResult.success({"path": str(target), "text": target.read_text(encoding="utf-8-sig")}).to_dict()
        except Exception as exc:
            return ApiResult.fail("READ_TEXT_FAILED", str(exc)).to_dict()

    def build_context(self, root_path: str, prompt: dict, extra_instruction: str = "") -> dict:
        try:
            config = load_config()
            scan = self.last_scan or fast_scan(root_path, config.exclude_rules)
            template = prompt.get("content", "{file_list}")
            if extra_instruction.strip():
                template = template.rstrip() + "\n\n" + extra_instruction.strip()
            return ApiResult.success(smart_output(scan, root_path, template)).to_dict()
        except Exception as exc:
            return ApiResult.fail("CONTEXT_BUILD_FAILED", str(exc)).to_dict()

    def export_text(self, root_path: str, filename: str, text: str) -> dict:
        try:
            target = Path(root_path).resolve() / filename
            target.write_text(text, encoding="utf-8")
            return ApiResult.success(str(target)).to_dict()
        except Exception as exc:
            return ApiResult.fail("EXPORT_FAILED", str(exc)).to_dict()

    def generate_plan(self, input_data: dict) -> dict:
        config = load_config()
        if input_data.get("provider"):
            config.provider = input_data["provider"]
        if input_data.get("model"):
            config.provider_models[config.provider] = input_data["model"]
        if input_data.get("timeoutSeconds"):
            config.ai_timeout_seconds = int(input_data["timeoutSeconds"])
        api_key = get_api_key(config.provider)
        prompt = input_data.get("userInstruction", "") + "\n\n" + input_data.get("fileListForAi", "")
        return send_to_ai(prompt, config, api_key, request_id=input_data.get("requestId", "")).to_dict()

    def generate_plan_stream(self, input_data: dict) -> dict:
        request_id = str(input_data.get("requestId") or "")
        if not request_id:
            return ApiResult.fail("REQUEST_ID_MISSING", "Request id is missing.").to_dict()
        with self.ai_stream_lock:
            self.ai_streams[request_id] = {"content": "", "done": False, "error": None}

        def append_chunk(text: str) -> None:
            with self.ai_stream_lock:
                if request_id in self.ai_streams:
                    self.ai_streams[request_id]["content"] += text

        def worker() -> None:
            config = load_config()
            if input_data.get("provider"):
                config.provider = input_data["provider"]
            if input_data.get("model"):
                config.provider_models[config.provider] = input_data["model"]
            if input_data.get("timeoutSeconds"):
                config.ai_timeout_seconds = int(input_data["timeoutSeconds"])
            api_key = get_api_key(config.provider)
            prompt = input_data.get("userInstruction", "") + "\n\n" + input_data.get("fileListForAi", "")
            result = send_to_ai(prompt, config, api_key, on_chunk=append_chunk, request_id=request_id)
            with self.ai_stream_lock:
                stream = self.ai_streams.get(request_id)
                if not stream:
                    return
                if result.ok:
                    if not stream["content"]:
                        stream["content"] = result.data or ""
                else:
                    stream["error"] = result.error.message if result.error else "AI request failed."
                stream["done"] = True

        threading.Thread(target=worker, daemon=True).start()
        return ApiResult.success({"requestId": request_id}).to_dict()

    def poll_ai_stream(self, request_id: str) -> dict:
        with self.ai_stream_lock:
            stream = self.ai_streams.get(request_id)
            if not stream:
                return ApiResult.fail("STREAM_NOT_FOUND", "AI stream not found.").to_dict()
            data = dict(stream)
            if stream.get("done"):
                self.ai_streams.pop(request_id, None)
        return ApiResult.success(data).to_dict()

    def cancel_ai_request(self, request_id: str) -> dict:
        cancelled = cancel_ai_request(request_id)
        with self.ai_stream_lock:
            stream = self.ai_streams.get(request_id)
            if stream is not None:
                stream["done"] = True
                stream["cancelled"] = True
                stream["error"] = None
                cancelled = True
        return ApiResult.success({"cancelled": cancelled}).to_dict()

    def parse_plan(self, json_text: str) -> dict:
        return parse_json(json_text).to_dict()

    def preview_plan(self, root_path: str, plan: dict) -> dict:
        try:
            parsed = _plan_from_dict(plan)
            return ApiResult.success(preview_actions(root_path, parsed)).to_dict()
        except Exception as exc:
            return ApiResult.fail("PREVIEW_FAILED", str(exc)).to_dict()

    def execute_plan(self, root_path: str, plan: dict, conflict_policy: str) -> dict:
        try:
            parsed = _plan_from_dict(plan)
            self.last_execute = execute_plan(root_path, parsed, conflict_policy)
            return ApiResult.success(self.last_execute).to_dict()
        except Exception as exc:
            return ApiResult.fail("EXECUTE_FAILED", str(exc)).to_dict()

    def undo_last(self) -> dict:
        if not self.last_execute:
            return ApiResult.fail("UNDO_NOT_AVAILABLE", "没有可撤销的操作。").to_dict()
        result = undo_plan("", self.last_execute)
        self.last_execute = None
        return ApiResult.success(result).to_dict()

    def load_config(self) -> dict:
        config = to_jsonable(load_config())
        config["api_keys"] = {provider: get_api_key(provider) for provider in ["anthropic", "openai", "custom"]}
        return ApiResult.success(config).to_dict()

    def load_history(self) -> dict:
        return ApiResult.success(load_history()).to_dict()

    def history_info(self) -> dict:
        path = history_path()
        return ApiResult.success({"path": str(path), "folder": str(path.parent)}).to_dict()

    def open_history_folder(self) -> dict:
        try:
            path = history_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path.parent))
            return ApiResult.success(str(path.parent)).to_dict()
        except Exception as exc:
            return ApiResult.fail("OPEN_HISTORY_FOLDER_FAILED", str(exc)).to_dict()

    def save_history(self, records: list[dict]) -> dict:
        save_history(records)
        return ApiResult.success(None).to_dict()

    def clear_history(self) -> dict:
        clear_history()
        return ApiResult.success(None).to_dict()

    def delete_history_records(self, record_ids: list[str]) -> dict:
        deleted = delete_history_records(record_ids)
        return ApiResult.success({"deleted": deleted}).to_dict()

    def save_config(self, config: dict) -> dict:
        merged = {**to_jsonable(load_config()), **config}
        api_keys = merged.pop("api_keys", {}) or {}
        endpoint_urls = merged.setdefault("provider_endpoint_urls", {})
        if merged.get("custom_endpoint_url") and not endpoint_urls.get("custom"):
            endpoint_urls["custom"] = merged["custom_endpoint_url"]
        merged["custom_endpoint_url"] = endpoint_urls.get("custom", "")
        merged.pop("apiKey", None)
        cfg = Config(**merged)
        save_config(cfg)
        for provider, key in api_keys.items():
            if provider in {"anthropic", "openai", "custom"}:
                set_api_key(provider, str(key or ""))
        if config.get("apiKey"):
            set_api_key(cfg.provider, config["apiKey"])
        return ApiResult.success(None).to_dict()

    def reset_config(self) -> dict:
        cfg = Config()
        save_config(cfg)
        for provider in ["anthropic", "openai", "custom"]:
            set_api_key(provider, "")
        data = to_jsonable(cfg)
        data["api_keys"] = {provider: "" for provider in ["anthropic", "openai", "custom"]}
        return ApiResult.success(data).to_dict()

    def test_connection(self, input_data: dict) -> dict:
        return test_connection(input_data).to_dict()

    def list_prompts(self) -> dict:
        return ApiResult.success(list_prompts()).to_dict()

    def save_prompt(self, prompt: dict) -> dict:
        return ApiResult.success(save_prompt(prompt)).to_dict()

    def delete_prompt(self, key: str) -> dict:
        delete_prompt(key)
        return ApiResult.success(None).to_dict()


def _plan_from_dict(plan: dict) -> Plan:
    if isinstance(plan, Plan):
        return plan
    result = parse_json(__import__("json").dumps(plan))
    if not result.ok:
        raise ValueError(result.error.message if result.error else "Invalid plan.")
    return result.data
