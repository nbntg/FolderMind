from __future__ import annotations

import json
import shutil
from pathlib import Path, PurePosixPath

from .scanner import generate_tree
from .types import (
    ActionResult,
    ApiResult,
    CreateDirAction,
    DeleteDirAction,
    ExecuteResult,
    MoveAction,
    Plan,
    PreviewResult,
    RenameAction,
    UndoAction,
    UndoResult,
)

SYSTEM_TRASH = {".DS_Store", "Thumbs.db", "desktop.ini", ".localized"}


def parse_json(json_text: str) -> ApiResult[Plan]:
    try:
        data = json.loads(_strip_fence(json_text))
    except json.JSONDecodeError as exc:
        return ApiResult.fail("JSON_PARSE_ERROR", "Invalid JSON.", str(exc))

    if not isinstance(data, dict):
        return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", "JSON must be an object with an actions array or a target folder tree.")

    if isinstance(data, dict) and "actions" not in data:
        report_plan = _try_file_management_summary_to_action_plan(data)
        if report_plan:
            if isinstance(report_plan, ApiResult):
                return report_plan
            data = report_plan
        else:
            tree_error = _validate_target_tree(data)
            if tree_error:
                return tree_error
            data = _target_tree_to_action_plan(data)

    if not isinstance(data.get("actions"), list):
        return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", "JSON must contain an actions array.")

    actions = []
    for index, raw in enumerate(data.get("actions", []), start=1):
        raw = _normalize_action_aliases(raw)
        error = _validate_raw_action(raw, index)
        if error:
            return error
        raw = {**raw, "id": raw.get("id", index)}
        kind = raw["type"]
        if kind == "create_dir":
            actions.append(CreateDirAction(raw["id"], kind, raw["path"], raw.get("reason")))
        elif kind == "move":
            actions.append(MoveAction(raw["id"], kind, raw.get("from", raw.get("from_path")), raw["to"], raw.get("reason")))
        elif kind == "rename":
            actions.append(RenameAction(raw["id"], kind, raw["path"], raw.get("from", raw.get("from_name")), raw["to"], raw.get("reason")))
        elif kind == "delete_dir":
            actions.append(DeleteDirAction(raw["id"], kind, raw["path"], raw.get("reason")))
        else:
            return ApiResult.fail("INVALID_ACTION_TYPE", f"Unsupported action type: {kind}")
    return ApiResult.success(Plan(actions=actions, summary=data.get("summary")))


def _normalize_action_aliases(raw):
    if not isinstance(raw, dict):
        return raw
    if "type" not in raw and "action" not in raw and len(raw) == 1:
        alias, payload = next(iter(raw.items()))
        if alias in {"move", "mkdir", "create_dir", "rename", "delete_dir", "rmdir"} and isinstance(payload, dict):
            raw = {"action": alias, **payload}
    normalized = dict(raw)
    accepts_root_relative_paths = "type" not in normalized and "action" in normalized
    if "type" not in normalized and "action" in normalized:
        normalized["type"] = normalized["action"]
    aliases = {
        "mkdir": "create_dir",
        "makedir": "create_dir",
        "make_dir": "create_dir",
        "create_folder": "create_dir",
        "delete_folder": "delete_dir",
        "rmdir": "delete_dir",
    }
    if isinstance(normalized.get("type"), str):
        normalized["type"] = aliases.get(normalized["type"].strip().lower(), normalized["type"].strip())
    for key in ("path", "from", "from_path", "from_name", "to"):
        if isinstance(normalized.get(key), str):
            normalized[key] = _normalize_plan_path(normalized[key], strip_leading_slash=accepts_root_relative_paths)
    return normalized


def _try_file_management_summary_to_action_plan(data: dict) -> dict | ApiResult | None:
    report = data.get("file_management_summary", data if "categories" in data else None)
    if report is None:
        return None
    if not isinstance(report, dict):
        return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", "无法识别格式：file_management_summary must be an object.")

    categories = report.get("categories")
    if not isinstance(categories, list) or not categories:
        return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", "无法识别格式：分类报告必须包含 categories 数组。")

    actions: list[dict] = []
    created_dirs: set[str] = set()

    def add_dir(path: str) -> None:
        normalized = _normalize_plan_path(path)
        if normalized and normalized not in created_dirs:
            actions.append({
                "id": len(actions) + 1,
                "type": "create_dir",
                "path": normalized,
                "reason": "Generated from file management summary.",
            })
            created_dirs.add(normalized)

    def add_file(source: str, target_dir: str) -> None:
        source_path = _normalize_plan_path(source)
        filename = PurePosixPath(source_path).name
        if not source_path or not filename:
            return
        actions.append({
            "id": len(actions) + 1,
            "type": "move",
            "from": source_path,
            "to": _normalize_plan_path(f"{target_dir}/{filename}"),
            "reason": "Generated from file management summary.",
        })

    def walk_category(category: dict, parent_dir: str = "", index: int = 0) -> ApiResult | None:
        if not isinstance(category, dict):
            return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", f"无法识别格式：categories[{index}] 必须是对象。")
        raw_name = category.get("category") or category.get("name") or category.get("title")
        if not isinstance(raw_name, str) or not raw_name.strip():
            return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", f"无法识别格式：categories[{index}] 缺少 category/name。")
        target_dir = _normalize_plan_path(f"{parent_dir}/{raw_name}" if parent_dir else raw_name)
        add_dir(target_dir)

        files = category.get("files", [])
        if files is None:
            files = []
        if not isinstance(files, list):
            return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", f"无法识别格式：{target_dir} 的 files 必须是数组。")
        for file_index, item in enumerate(files, start=1):
            if isinstance(item, str):
                filename = item
            elif isinstance(item, dict):
                filename = item.get("filename") or item.get("path") or item.get("name")
            else:
                return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", f"无法识别格式：{target_dir} 的第 {file_index} 个文件不是字符串或对象。")
            if not isinstance(filename, str) or not filename.strip():
                return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", f"无法识别格式：{target_dir} 的第 {file_index} 个文件缺少 filename。")
            add_file(filename, target_dir)

        children = category.get("categories") or category.get("children") or []
        if children is None:
            children = []
        if not isinstance(children, list):
            return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", f"无法识别格式：{target_dir} 的子分类必须是数组。")
        for child_index, child in enumerate(children, start=1):
            error = walk_category(child, target_dir, child_index)
            if error:
                return error
        return None

    for index, category in enumerate(categories, start=1):
        error = walk_category(category, "", index)
        if error:
            return error

    if not any(action["type"] == "move" for action in actions):
        return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", "无法识别格式：分类报告没有可移动的文件。")

    return {
        "summary": "Converted file management summary into executable actions.",
        "actions": actions,
    }


def _target_tree_to_action_plan(data: dict) -> dict:
    actions: list[dict] = []
    created_dirs: set[str] = set()

    def add_dir(path: str) -> None:
        normalized = _normalize_plan_path(path)
        if not normalized or normalized in created_dirs:
            return
        actions.append({
            "id": len(actions) + 1,
            "type": "create_dir",
            "path": normalized,
            "reason": "Generated from target folder structure JSON.",
        })
        created_dirs.add(normalized)

    def add_move(source: str, target_dir: str) -> None:
        source_path = _normalize_plan_path(source)
        if not source_path:
            return
        filename = PurePosixPath(source_path).name
        target = _normalize_plan_path(f"{target_dir}/{filename}" if target_dir else filename)
        if source_path == target:
            return
        actions.append({
            "id": len(actions) + 1,
            "type": "move",
            "from": source_path,
            "to": target,
            "reason": "Generated from target folder structure JSON.",
        })

    def walk(node, current_dir: str = "") -> None:
        if isinstance(node, dict):
            for name, child in node.items():
                if name in {"summary", "description"}:
                    continue
                next_dir = _normalize_plan_path(f"{current_dir}/{name}" if current_dir else str(name))
                add_dir(next_dir)
                walk(child, next_dir)
            return
        if isinstance(node, list):
            for item in node:
                if isinstance(item, str):
                    add_move(item, current_dir)
                else:
                    walk(item, current_dir)
            return
        if isinstance(node, str):
            add_move(node, current_dir)

    walk(data)
    return {"summary": "Converted target folder structure JSON into executable actions.", "actions": actions}


def _normalize_plan_path(path: str, strip_leading_slash: bool = True) -> str:
    value = str(path).replace("\\", "/").strip()
    if strip_leading_slash:
        value = value.strip("/")
    else:
        value = value.rstrip("/")
    return PurePosixPath(value).as_posix()


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _validate_target_tree(node) -> ApiResult | None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"summary", "description"}:
                continue
            if isinstance(value, (int, float, bool)) or value is None:
                return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", f"Unsupported target tree value at {key}. Use FolderMind actions JSON instead.")
            error = _validate_target_tree(value)
            if error:
                return error
        return None
    if isinstance(node, list):
        for item in node:
            if not isinstance(item, (str, dict, list)):
                return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", "Unsupported item in target folder tree. Use FolderMind actions JSON instead.")
            error = _validate_target_tree(item)
            if error:
                return error
        return None
    if isinstance(node, str):
        return None
    return ApiResult.fail("UNSUPPORTED_JSON_SHAPE", "Unsupported JSON shape. Use FolderMind actions JSON instead.")


def _validate_raw_action(raw: dict, index: int = 0) -> ApiResult | None:
    label = f"actions[{index}]"
    if not isinstance(raw, dict):
        return ApiResult.fail("ACTION_INVALID", f"{label} must be an object.")
    if not raw.get("type"):
        return ApiResult.fail("ACTION_FIELD_MISSING", f"{label}.type is required.")
    kind = raw["type"]
    required_by_type = {
        "create_dir": ("path",),
        "move": ("from", "to"),
        "rename": ("path", "from", "to"),
        "delete_dir": ("path",),
    }
    if kind not in required_by_type:
        return ApiResult.fail("INVALID_ACTION_TYPE", f"Unsupported action type at {label}: {kind}")
    for field in required_by_type[kind]:
        aliases = {"from": ("from", "from_path", "from_name")}.get(field, (field,))
        if not any(raw.get(alias) for alias in aliases):
            return ApiResult.fail("ACTION_FIELD_MISSING", f"{label}.{field} is required.")
    path_values: list[str] = []
    for key in ("path", "from", "from_path", "from_name", "to"):
        if key in raw:
            path_values.append(raw[key])
    for value in path_values:
        normalized = value.replace("\\", "/")
        if Path(value).is_absolute() or normalized.startswith("/"):
            return ApiResult.fail("ABSOLUTE_PATH_NOT_ALLOWED", f"Absolute path is not allowed: {value}")
        if ".." in PurePosixPath(normalized).parts:
            return ApiResult.fail("PATH_TRAVERSAL", f"Path traversal is not allowed: {value}")
    return None


def preview_actions(root_path: str, plan: Plan) -> PreviewResult:
    root = Path(root_path).resolve()
    before_paths = _paths_from_disk(root)
    after_paths = set(before_paths)
    missing = []
    conflicts = []
    lines = []
    for action in plan.actions:
        description = _describe(action)
        target = _target_for(root, action)
        source = _source_for(root, action)
        if source and not source.exists():
            missing.append(str(source.relative_to(root)).replace("\\", "/"))
        has_conflict = bool(target and target.exists() and source != target)
        if has_conflict and action.type in {"move", "rename"}:
            conflicts.append({"actionId": action.id, "sourcePath": str(source), "targetPath": str(target), "type": action.type})
        lines.append({"actionId": action.id, "description": description, "hasConflict": has_conflict})
        _simulate(after_paths, action)
    return PreviewResult(_tree_from_paths(root, before_paths), _tree_from_paths(root, after_paths), lines, conflicts, missing)


def execute_plan(root_path: str, plan: Plan, conflict_policy: str) -> ExecuteResult:
    root = Path(root_path).resolve()
    results: list[ActionResult] = []
    undo_stack: list[UndoAction] = []
    for action in plan.actions:
        try:
            result, undo = _execute_one(root, action, conflict_policy)
            results.append(result)
            if isinstance(undo, list):
                undo_stack.extend(undo)
            elif undo:
                undo_stack.append(undo)
        except Exception as exc:
            results.append(ActionResult(action.id, "error", f"UNKNOWN_ERROR: {exc}"))
    return ExecuteResult(
        results=results,
        success_count=sum(r.status == "success" for r in results),
        skipped_count=sum(r.status == "skipped" for r in results),
        error_count=sum(r.status == "error" for r in results),
        undo_available=bool(undo_stack),
        undo_stack=undo_stack,
    )


def _execute_one(root: Path, action, conflict_policy: str) -> tuple[ActionResult, UndoAction | list[UndoAction] | None]:
    if action.type == "create_dir":
        target = _safe_join(root, action.path)
        if target.exists() and target.is_file():
            return ActionResult(action.id, "error", "TARGET_EXISTS: target is a file"), None
        created_dirs = _created_directories_for(root, target)
        target.mkdir(parents=True, exist_ok=True)
        undo = [UndoAction("remove_dir", action.id, str(path)) for path in created_dirs]
        return ActionResult(action.id, "success", "Directory ready.", str(target)), undo

    if action.type == "move":
        source = _safe_join(root, action.from_path)
        target = _safe_join(root, action.to)
        if not source.exists():
            return ActionResult(action.id, "error", "SOURCE_NOT_FOUND"), None
        if not target.parent.exists():
            return ActionResult(action.id, "error", "PARENT_DIR_NOT_FOUND"), None
        target = _resolve_conflict(target, conflict_policy)
        if target is None:
            return ActionResult(action.id, "skipped", "TARGET_EXISTS"), None
        shutil.move(str(source), str(target))
        return ActionResult(action.id, "success", "Moved.", str(target)), UndoAction("move", action.id, str(target), str(source))

    if action.type == "rename":
        source = _safe_join(root, action.path) / action.from_name
        target = _safe_join(root, action.path) / action.to
        if not source.exists():
            return ActionResult(action.id, "error", "SOURCE_NOT_FOUND"), None
        target = _resolve_conflict(target, conflict_policy)
        if target is None:
            return ActionResult(action.id, "skipped", "TARGET_EXISTS"), None
        source.rename(target)
        return ActionResult(action.id, "success", "Renamed.", str(target)), UndoAction("rename", action.id, str(target), str(source))

    if action.type == "delete_dir":
        target = _safe_join(root, action.path)
        if not target.exists():
            return ActionResult(action.id, "success", "Directory already absent."), None
        if not target.is_dir():
            return ActionResult(action.id, "error", "TARGET_NOT_DIRECTORY"), None
        for child in target.iterdir():
            if child.name not in SYSTEM_TRASH:
                return ActionResult(action.id, "error", "DIRECTORY_NOT_EMPTY"), None
        for child in target.iterdir():
            child.unlink()
        target.rmdir()
        return ActionResult(action.id, "success", "Deleted empty directory."), UndoAction("delete_dir_restore", action.id, str(target))

    return ActionResult(action.id, "error", "INVALID_ACTION_TYPE"), None


def undo_plan(root_path: str, exec_result: ExecuteResult) -> UndoResult:
    details = []
    for undo in reversed(exec_result.undo_stack):
        try:
            if undo.type in {"move", "rename"} and undo.to:
                Path(undo.from_path).rename(Path(undo.to))
            elif undo.type == "remove_dir":
                target = Path(undo.from_path)
                if target.exists() and target.is_dir() and not any(target.iterdir()):
                    target.rmdir()
                elif target.exists():
                    details.append(ActionResult(undo.original_action_id, "skipped", "UNDO_SKIPPED_DIRECTORY_NOT_EMPTY", str(target)))
                    continue
            elif undo.type == "delete_dir_restore":
                Path(undo.from_path).mkdir(parents=True, exist_ok=True)
            details.append(ActionResult(undo.original_action_id, "success", "Undone."))
        except Exception as exc:
            details.append(ActionResult(undo.original_action_id, "error", f"UNDO_FAILED: {exc}"))
    return UndoResult(sum(r.status == "success" for r in details), sum(r.status == "skipped" for r in details), details)


def validate_actions(root_path: str, plan: Plan, conflict_policy: str) -> dict:
    return {"ok": True, "preview": preview_actions(root_path, plan)}


def _safe_join(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise ValueError("PATH_TRAVERSAL")
    return target


def _created_directories_for(root: Path, target: Path) -> list[Path]:
    if target.exists():
        return []
    relative = target.relative_to(root)
    created: list[Path] = []
    current = root
    for part in relative.parts:
        current = current / part
        if not current.exists():
            created.append(current)
    return created


def _resolve_conflict(target: Path, conflict_policy: str) -> Path | None:
    if not target.exists():
        return target
    if conflict_policy == "skip" or conflict_policy == "ask":
        return None
    if conflict_policy == "auto_rename":
        return _auto_rename(target)
    return None


def _auto_rename(target: Path) -> Path:
    stem, suffix = target.stem, target.suffix
    counter = 1
    while True:
        candidate = target.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _source_for(root: Path, action):
    if action.type == "move":
        return root / action.from_path
    if action.type == "rename":
        return root / action.path / action.from_name
    if action.type == "delete_dir":
        return root / action.path
    return None


def _target_for(root: Path, action):
    if action.type == "create_dir":
        return root / action.path
    if action.type == "move":
        return root / action.to
    if action.type == "rename":
        return root / action.path / action.to
    return None


def _describe(action) -> str:
    if action.type == "create_dir":
        return f"Create folder {action.path}"
    if action.type == "move":
        return f"Move {action.from_path} to {action.to}"
    if action.type == "rename":
        return f"Rename {action.from_name} to {action.to}"
    return f"Delete folder {action.path}"


def _tree_from_disk(root: Path) -> str:
    return _tree_from_paths(root, _paths_from_disk(root))


def _paths_from_disk(root: Path) -> set[str]:
    return {child.relative_to(root).as_posix() for child in root.rglob("*") if child.is_file()}


def _tree_from_paths(root: Path, paths: set[str]) -> str:
    from .types import FileEntry
    files = [FileEntry(path, str(root / path), Path(path).name, 0, "", False) for path in sorted(paths)]
    return generate_tree(str(root), files)


def _simulate(paths: set[str], action) -> None:
    if action.type == "move":
        if action.from_path in paths:
            paths.remove(action.from_path)
            paths.add(action.to)
    elif action.type == "rename":
        old = PurePosixPath(action.path.replace("\\", "/")) / action.from_name
        new = PurePosixPath(action.path.replace("\\", "/")) / action.to
        old_s = old.as_posix().lstrip("./")
        new_s = new.as_posix().lstrip("./")
        if old_s in paths:
            paths.remove(old_s)
            paths.add(new_s)
    elif action.type == "delete_dir":
        prefix = action.path.strip("/").replace("\\", "/") + "/"
        for path in list(paths):
            if path.startswith(prefix):
                paths.remove(path)
