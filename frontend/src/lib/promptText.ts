import type { Language, PromptItem } from './types';

export const JSON_RULES_ZH = `你必须只返回 FolderMind 可执行的 JSON，不要输出解释、Markdown、代码块或任何额外文字。

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
14. 输出前自查：① 文件列表中是否还有文件未出现在 actions 里？② 每个执行了 move 的原目录，若已清空，是否补了对应的 delete_dir？③ 所有 from 路径是否与文件列表完全一致？自查通过后再输出。`;

export const JSON_RULES_EN = `Return only FolderMind executable JSON. Do not output explanations, Markdown, code fences, or any extra text.

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
14. Before output, self-check: (1) Is every file from the file list included in actions? (2) For each source folder emptied by move actions, did you add the matching delete_dir? (3) Does every from path exactly match the file list? Output only after this check passes.`;

export function customPromptTemplate(language: Language) {
  if (language === 'en') {
    return `You are FolderMind's file organization planning assistant.
Below is the user's selected file list. Each entry contains relative path, size, and modified time.

[File list]
{file_list}

Write your organization style requirements here. Do not remove the file list placeholder or JSON rules below.

${JSON_RULES_EN}`;
  }
  return `你是 FolderMind 的文件整理规划助手。
下面是用户选择的文件列表，格式为：相对路径、大小、修改时间。

[文件列表]
{file_list}

请在这里写你的整理风格要求。不要删除下面的文件列表占位符和 JSON 规则。

${JSON_RULES_ZH}`;
}

export function createCustomPromptDraft(language: Language, displayName: string): PromptItem {
  const contentZh = customPromptTemplate('zh-CN');
  const contentEn = customPromptTemplate('en');
  return {
    key: '',
    name: displayName,
    content: language === 'en' ? contentEn : contentZh,
    name_zh: language === 'en' ? '新建提示词' : displayName,
    name_en: language === 'en' ? displayName : 'New Prompt',
    content_zh: contentZh,
    content_en: contentEn,
    is_preset: false
  };
}

export function promptName(prompt: PromptItem, language: Language) {
  return language === 'en'
    ? prompt.name_en || prompt.name
    : prompt.name_zh || prompt.name;
}

export function promptContent(prompt: PromptItem, language: Language) {
  return language === 'en'
    ? prompt.content_en || prompt.content
    : prompt.content_zh || prompt.content;
}

export function localizedPrompt(prompt: PromptItem, language: Language): PromptItem {
  return {
    ...prompt,
    name: promptName(prompt, language),
    content: promptContent(prompt, language)
  };
}
