from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Generic, Literal, Optional, TypeVar, Union

T = TypeVar("T")


@dataclass
class ApiError:
    code: str
    message: str
    details: Optional[Any] = None

    def to_dict(self) -> dict:
        data = {"code": self.code, "message": self.message}
        if self.details is not None:
            data["details"] = self.details
        return data


@dataclass
class ApiResult(Generic[T]):
    ok: bool
    data: Optional[T] = None
    error: Optional[ApiError] = None

    @staticmethod
    def success(data: T = None) -> "ApiResult[T]":
        return ApiResult(ok=True, data=data)

    @staticmethod
    def fail(code: str, message: str, details: Any = None) -> "ApiResult":
        return ApiResult(ok=False, error=ApiError(code, message, details))

    def to_dict(self) -> dict:
        data: dict[str, Any] = {"ok": self.ok}
        if self.data is not None:
            data["data"] = to_jsonable(self.data)
        if self.error is not None:
            data["error"] = self.error.to_dict()
        return data


@dataclass
class FileEntry:
    relative_path: str
    absolute_path: str
    name: str
    size: int
    modified_time: str
    is_dir: bool = False


@dataclass
class DuplicateGroup:
    hash: str
    files: list[FileEntry]


@dataclass
class ScanResult:
    root_path: str
    files: list[FileEntry]
    tree_text: str
    duplicates: list[DuplicateGroup]
    warnings: list[str]
    file_count: int


@dataclass
class CreateDirAction:
    id: int
    type: Literal["create_dir"]
    path: str
    reason: Optional[str] = None


@dataclass
class MoveAction:
    id: int
    type: Literal["move"]
    from_path: str
    to: str
    reason: Optional[str] = None


@dataclass
class RenameAction:
    id: int
    type: Literal["rename"]
    path: str
    from_name: str
    to: str
    reason: Optional[str] = None


@dataclass
class DeleteDirAction:
    id: int
    type: Literal["delete_dir"]
    path: str
    reason: Optional[str] = None


Action = Union[CreateDirAction, MoveAction, RenameAction, DeleteDirAction]


@dataclass
class Plan:
    actions: list[Action]
    summary: Optional[str] = None


ActionStatus = Literal["success", "skipped", "error"]
ConflictPolicy = Literal["ask", "auto_rename", "skip"]


@dataclass
class ActionResult:
    action_id: int
    status: ActionStatus
    message: str
    final_path: Optional[str] = None


@dataclass
class UndoAction:
    type: str
    original_action_id: int
    from_path: str
    to: Optional[str] = None


@dataclass
class ExecuteResult:
    results: list[ActionResult]
    success_count: int
    skipped_count: int
    error_count: int
    undo_available: bool
    undo_stack: list[UndoAction] = field(default_factory=list)


@dataclass
class UndoResult:
    restored_count: int
    skipped_count: int
    details: list[ActionResult]


@dataclass
class PreviewResult:
    before_tree_text: str
    after_tree_text: str
    lines: list[dict]
    conflicts: list[dict]
    missing_paths: list[str]


@dataclass
class Config:
    provider: str = "anthropic"
    provider_models: dict[str, str] = field(default_factory=lambda: {
        "anthropic": "claude-opus-4-6",
        "openai": "gpt-4o",
        "custom": "",
    })
    provider_endpoint_urls: dict[str, str] = field(default_factory=lambda: {
        "anthropic": "https://api.anthropic.com/v1/messages",
        "openai": "https://api.openai.com/v1/chat/completions",
        "custom": "",
    })
    custom_models: dict[str, list[str]] = field(default_factory=lambda: {
        "anthropic": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        "openai": ["gpt-4o", "gpt-4.1", "o3"],
        "custom": [],
    })
    custom_endpoint_url: str = ""
    conflict_policy: str = "ask"
    exclude_rules: list[str] = field(default_factory=list)
    language: str = "zh-CN"
    theme: str = "dark"
    config_version: int = 1
    deleted_preset_keys: list[str] = field(default_factory=list)
    custom_prompts: list[dict] = field(default_factory=list)
    history_retention_limit: int = 100
    save_unexecuted_ai_plans: bool = False
    save_raw_ai_responses: bool = False
    ai_timeout_seconds: int = 60
    ai_context_file_limit: int = 1000


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {k: to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    return value
