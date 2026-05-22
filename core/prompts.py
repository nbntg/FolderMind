from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import load_config, save_config


@dataclass
class PromptItem:
    key: str
    name: str
    content: str
    is_preset: bool = False
    is_deleted: bool = False
    name_zh: str = ""
    name_en: str = ""
    content_zh: str = ""
    content_en: str = ""
    desc_zh: str = ""
    desc_en: str = ""


JSON_RULES_ZH = """
你必须只返回 FolderMind 可执行的 JSON，不要输出解释、Markdown、代码块或任何额外文字。

允许的 JSON 格式：
{
  "summary": "一句话说明整理思路",
  "actions": [
    {"id": 1, "type": "create_dir", "path": "目标文件夹", "reason": "原因"},
    {"id": 2, "type": "move", "from": "原相对路径/文件.pdf", "to": "目标相对路径/文件.pdf", "reason": "原因"},
    {"id": 3, "type": "rename", "path": "所在相对目录", "from": "旧文件名.jpg", "to": "新文件名.jpg", "reason": "原因"},
    {"id": 4, "type": "delete_dir", "path": "要删除的空文件夹", "reason": "原因"}
  ]
}

严格规则：
1. 所有路径必须使用正斜杠 /，并且必须是相对于根目录的相对路径，不要以 / 开头。
2. move.from 必须与文件列表中的路径完全一致，不得猜测、改写或补全不存在的文件名。
3. move.to 必须包含目标文件名，不能只写文件夹。
4. rename 只能改文件名，path 是所在目录，from/to 只能是文件名。
5. 不要删除任何文件，delete_dir 只能删除已经清空的文件夹。
6. 如需删除原文件夹，顺序必须是 create_dir -> move -> delete_dir。
7. 不要引用文件列表里不存在的文件。
8. 如果文件列表为空，返回 {"summary":"无需整理","actions":[]}；如果文件列表不为空，即使没有必要改变位置，也必须按第 11 条覆盖所有文件。
9. id 必须从 1 开始连续递增。
10. 只输出 JSON。
11. 文件列表中的每一个文件都必须出现在 actions 中，不得遗漏任何文件。即使文件保持原位，也要用 move 把它移动到最终相对路径；如果最终位置不变，则 from 和 to 可以相同。
12. 对于只包含单个文件的子文件夹（下载工具自动生成的包装文件夹），必须拆解处理：先用 move 将文件移到对应主题目录（路径中去掉原子文件夹层级），再用 delete_dir 删除已清空的原子文件夹。不允许将整个子文件夹作为整体移动，必须操作到具体文件。
13. 允许的 action type 只有以下四种，不得自创其他类型：create_dir、move、rename、delete_dir。
14. 输出前自查：① 文件列表中是否还有文件未出现在 actions 里？② 每个执行了 move 的原目录，若已清空，是否补了对应的 delete_dir？③ 所有 from 路径是否与文件列表完全一致？自查通过后再输出。
""".strip()


JSON_RULES_EN = """
Return only FolderMind executable JSON. Do not output explanations, Markdown, code fences, or any extra text.

Allowed JSON shape:
{
  "summary": "One-sentence organization rationale",
  "actions": [
    {"id": 1, "type": "create_dir", "path": "target folder", "reason": "reason"},
    {"id": 2, "type": "move", "from": "source relative/path.pdf", "to": "target relative/path.pdf", "reason": "reason"},
    {"id": 3, "type": "rename", "path": "containing relative folder", "from": "old-name.jpg", "to": "new-name.jpg", "reason": "reason"},
    {"id": 4, "type": "delete_dir", "path": "empty folder to delete", "reason": "reason"}
  ]
}

Strict rules:
1. Use forward slashes / and relative paths from the selected root folder only. Do not start paths with /.
2. move.from must exactly match one path from the file list. Do not invent, rewrite, or complete filenames.
3. move.to must include the target filename, not just a folder.
4. rename may only change a filename. path is the containing folder; from/to are filenames only.
5. Never delete files. delete_dir may only remove folders that are already empty.
6. If an original folder should be removed, action order must be create_dir -> move -> delete_dir.
7. Do not reference files that are not present in the file list.
8. If the file list is empty, return {"summary":"No changes needed","actions":[]}. If the file list is not empty, still cover every file according to rule 11, even when no location changes are needed.
9. id values must start at 1 and increase continuously.
10. Output JSON only.
11. Every file in the file list must appear in actions. Do not omit any file. Even if a file stays in place, include a move action to its final relative path; if the final location is unchanged, from and to may be identical.
12. For a subfolder that contains only one file, usually created by a downloader as a wrapper folder, break it apart: first move that file into the appropriate topic folder with the wrapper folder removed from the path, then delete the emptied wrapper folder with delete_dir. Do not move the whole subfolder as one unit; operate on the concrete file.
13. The only allowed action types are: create_dir, move, rename, delete_dir. Do not invent any other type.
14. Before output, self-check: (1) Is every file from the file list included in actions? (2) For each source folder emptied by move actions, did you add the matching delete_dir? (3) Does every from path exactly match the file list? Output only after this check passes.
""".strip()


CUSTOM_TASK_ZH = "请在这里写你的整理风格要求。不要删除下面的文件列表占位符和 JSON 规则。"
CUSTOM_TASK_EN = "Write your organization style requirements here. Do not remove the file list placeholder or JSON rules below."


def _prompt(zh_task: str, en_task: str) -> tuple[str, str]:
    zh = (
        "你是 FolderMind 的文件整理规划助手。\n"
        "下面是用户选择的文件列表，格式为：相对路径、大小、修改时间。\n\n"
        "[文件列表]\n{file_list}\n\n"
        f"{zh_task}\n\n"
        f"{JSON_RULES_ZH}"
    )
    en = (
        "You are FolderMind's file organization planning assistant.\n"
        "Below is the user's selected file list. Each entry contains relative path, size, and modified time.\n\n"
        "[File list]\n{file_list}\n\n"
        f"{en_task}\n\n"
        f"{JSON_RULES_EN}"
    )
    return zh, en


def custom_prompt_template() -> tuple[str, str]:
    return _prompt(CUSTOM_TASK_ZH, CUSTOM_TASK_EN)


def _preset(key: str, name_zh: str, name_en: str, desc_zh: str, desc_en: str, zh_task: str, en_task: str) -> PromptItem:
    content_zh, content_en = _prompt(zh_task, en_task)
    return PromptItem(
        key=key,
        name=name_zh,
        content=content_zh,
        is_preset=True,
        name_zh=name_zh,
        name_en=name_en,
        content_zh=content_zh,
        content_en=content_en,
        desc_zh=desc_zh,
        desc_en=desc_en,
    )


PRESETS = [
    _preset(
        "organize",
        "整理归类",
        "Organize by Category",
        "按用途和内容建立清晰目录结构",
        "Create a clear folder structure by purpose and content",
        "请按文件用途、主题和类型分类，建立清晰、低风险、便于长期维护的文件夹结构。",
        "Group files by purpose, topic, and type. Create a clear, low-risk folder structure that is easy to maintain.",
    ),
    _preset(
        "study",
        "学习计划",
        "Study Plan",
        "按课程、主题、资料类型和优先级整理学习资料",
        "Organize learning materials by course, topic, type, and priority",
        "请识别学习资料主题，按课程、知识领域、资料类型和学习优先级整理。",
        "Organize learning materials by course, knowledge area, material type, and study priority.",
    ),
    _preset(
        "archive",
        "归档清理",
        "Archive Cleanup",
        "把旧资料和低频文件移动到归档目录",
        "Move old or low-frequency files into archive folders",
        "请找出适合归档的旧文件和低频文件，移动到归档目录。近期文件和不确定文件保持原位。",
        "Find old or low-frequency files suitable for archiving and move them into archive folders. Keep recent or uncertain files in place.",
    ),
    _preset(
        "project",
        "项目整理",
        "Project Structure",
        "按项目规范整理代码、文档、素材和配置",
        "Organize code, documents, assets, and configuration by project conventions",
        "请识别代码、文档、素材、配置、输出物和临时文件，按项目结构整理，例如 src、docs、assets、config、output。",
        "Identify code, documents, assets, configuration, outputs, and temporary files. Organize them into project-style folders such as src, docs, assets, config, and output.",
    ),
    _preset(
        "rename",
        "重命名规范",
        "Rename Rules",
        "统一混乱文件名，保持可读和低风险",
        "Normalize messy filenames while keeping them readable and low-risk",
        "请找出命名混乱但内容含义明确的文件，提出清晰、可读、低风险的 rename 方案。已经清晰的文件名不要改。",
        "Find files with messy but understandable names and propose clear, readable, low-risk rename actions. Do not rename files that are already clear.",
    ),
]


def _localized(item: dict, language: str) -> dict:
    use_en = language == "en"
    result = dict(item)
    result["name"] = item.get("name_en" if use_en else "name_zh") or item.get("name", "")
    result["content"] = item.get("content_en" if use_en else "content_zh") or item.get("content", "")
    return result


def list_prompts() -> list[dict]:
    config = load_config()
    deleted = set(config.deleted_preset_keys)
    presets = [_localized(asdict(p), config.language) for p in PRESETS if p.key not in deleted]
    custom = [_localized(prompt, config.language) for prompt in config.custom_prompts]
    return presets + custom


def save_prompt(prompt: dict) -> dict:
    config = load_config()
    name = prompt.get("name", "Custom prompt")
    content = prompt.get("content", "")
    default_zh, default_en = custom_prompt_template()
    item = {
        "key": prompt.get("key") or f"custom-{len(config.custom_prompts) + 1}",
        "name": name,
        "content": content or (default_en if config.language == "en" else default_zh),
        "name_zh": prompt.get("name_zh") or name,
        "name_en": prompt.get("name_en") or name,
        "content_zh": prompt.get("content_zh") or content or default_zh,
        "content_en": prompt.get("content_en") or content or default_en,
        "is_preset": False,
    }
    config.custom_prompts = [p for p in config.custom_prompts if p.get("key") != item["key"]]
    config.custom_prompts.append(item)
    save_config(config)
    return _localized(item, config.language)


def delete_prompt(key: str) -> None:
    config = load_config()
    if any(p.key == key for p in PRESETS):
        if key not in config.deleted_preset_keys:
            config.deleted_preset_keys.append(key)
    else:
        config.custom_prompts = [p for p in config.custom_prompts if p.get("key") != key]
    save_config(config)
