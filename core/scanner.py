from __future__ import annotations

import fnmatch
import hashlib
import os
from datetime import datetime
from pathlib import Path

from .types import DuplicateGroup, FileEntry, ScanResult

DEFAULT_EXCLUDES = {
    ".git",
    ".svn",
    ".hg",
    ".idea",
    ".vscode",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "target",
    "dist",
    "build",
}


class ScanCancelled(Exception):
    pass


def fast_scan(path: str, exclude_rules: list[str], progress_callback=None, should_cancel=None, _override_count=None) -> ScanResult:
    root = Path(path).resolve()
    files: list[FileEntry] = []
    warnings: list[str] = []
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Not a folder: {path}")

    for current, dirnames, filenames in os.walk(root):
        if should_cancel and should_cancel():
            raise ScanCancelled()
        current_path = Path(current)
        dirnames[:] = [
            d for d in sorted(dirnames)
            if not _is_excluded((current_path / d).relative_to(root).as_posix(), d, exclude_rules, is_dir=True)
        ]
        for filename in sorted(filenames):
            if should_cancel and should_cancel():
                raise ScanCancelled()
            if _is_excluded((current_path / filename).relative_to(root).as_posix(), filename, exclude_rules, is_dir=False):
                continue
            full = current_path / filename
            stat = full.stat()
            rel = full.relative_to(root).as_posix()
            files.append(FileEntry(
                relative_path=rel,
                absolute_path=str(full),
                name=filename,
                size=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                is_dir=False,
            ))
            if progress_callback and len(files) % 100 == 0:
                _report_progress(progress_callback, len(files), rel)

    file_count = _override_count if _override_count is not None else len(files)
    if file_count > 50000:
        warnings.append("Large folder: scanning was capped for AI prompt safety.")
    return ScanResult(str(root), files, generate_tree(str(root), files), find_duplicates(files), warnings, file_count)


def _report_progress(progress_callback, count: int, current_path: str) -> None:
    try:
        progress_callback(count, current_path)
    except TypeError:
        progress_callback(count)


def _is_excluded(relative_path: str, name: str, rules: list[str], is_dir: bool) -> bool:
    if name in DEFAULT_EXCLUDES:
        return True
    for rule in rules:
        clean = rule.strip().replace("\\", "/")
        if not clean:
            continue
        if clean.endswith("/") and is_dir and fnmatch.fnmatch(relative_path + "/", clean):
            return True
        if fnmatch.fnmatch(relative_path, clean) or fnmatch.fnmatch(name, clean):
            return True
    return False


def find_duplicates(files: list[FileEntry]) -> list[DuplicateGroup]:
    by_size: dict[int, list[FileEntry]] = {}
    for file in files:
        if file.size > 0:
            by_size.setdefault(file.size, []).append(file)

    duplicates: list[DuplicateGroup] = []
    for same_size in by_size.values():
        if len(same_size) < 2:
            continue
        by_hash: dict[str, list[FileEntry]] = {}
        for file in same_size:
            digest = hashlib.sha1(Path(file.absolute_path).read_bytes()).hexdigest()
            by_hash.setdefault(digest, []).append(file)
        duplicates.extend(DuplicateGroup(h, group) for h, group in by_hash.items() if len(group) > 1)
    return duplicates


def generate_tree(root_path: str, files: list[FileEntry]) -> str:
    root_name = Path(root_path).name or root_path
    lines = [f"{root_name}/"]
    seen_dirs: set[str] = set()
    for file in sorted(files, key=lambda f: f.relative_path):
        parts = file.relative_path.split("/")
        for index, folder in enumerate(parts[:-1]):
            folder_path = "/".join(parts[: index + 1])
            if folder_path not in seen_dirs:
                lines.append(f"{'  ' * index}{folder}/")
                seen_dirs.add(folder_path)
        depth = len(parts) - 1
        lines.append(f"{'  ' * depth}- {parts[-1]}")
    return "\n".join(lines)


def generate_for_ai(files: list[FileEntry]) -> str:
    return "\n".join(f"- {f.relative_path} ({f.size} bytes)" for f in sorted(files, key=lambda item: item.relative_path))


def smart_output(scan_result: ScanResult, root_path: str, prompt_template: str) -> dict:
    text = prompt_template.replace("{file_list}", generate_for_ai(scan_result.files))
    if scan_result.file_count <= 500 and len(text) <= 120_000:
        return {"action": "copy", "text": text, "file_count": scan_result.file_count}
    export_path = str(Path(root_path) / "foldermind_ai_context.md")
    Path(export_path).write_text(text, encoding="utf-8")
    return {"action": "export", "text": text, "export_path": export_path}
