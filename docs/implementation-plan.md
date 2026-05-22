# FolderMind — 实现计划（implementation-plan.md）

> 本文档描述“如何一步步生成项目”。
> 产品目标见 `docs/spec.md`；接口和数据格式见 `docs/contracts.md`。

---

## 给代码生成 Agent 的工作规则

在开始任何实现之前，必须阅读并遵守以下规则：

1. **优先生成可运行 MVP**，不要一次性实现所有增强功能（历史页、i18n、打包等属于 Phase 5）
2. **所有文件操作必须先写测试**（TDD：写失败测试 → 确认失败 → 最小实现 → 确认通过 → commit）
3. **后端核心逻辑必须能脱离 GUI 独立测试**（pytest 不启动 pywebview）
4. **前后端共享的数据结构以 `docs/contracts.md` 为准**，若 spec.md 与之冲突，以 contracts.md 为准
5. **不允许实现文档未列出的危险功能**，包括：覆盖文件、递归删除非空目录、读取文件正文、上传文件内容
6. **每个阶段完成后必须运行对应测试**，测试未通过不得进入下一阶段
7. **UI 先朴素可用，再做视觉优化**；核心流程稳定比视觉美观更重要
8. **对不确定的地方选择更保守的实现**，不要自行扩大范围

---

## 已确认的关键决策

在实现前已明确以下决策，代码实现必须与此一致：

| 问题 | 决策 |
|---|---|
| MVP 是否支持覆盖已有文件 | **否**。冲突只允许自动重命名或跳过 |
| `move` 父目录不存在时 | **报错 `PARENT_DIR_NOT_FOUND`**，不自动创建，要求 AI 先输出 `create_dir` |
| 历史页和持久化撤销 | **不进 MVP**，放入 Phase 5 |
| 第一版 AI 接入策略 | **MVP 必须接入真实 AI API；粘贴/导入 JSON 作为备用和调试入口** |
| 目标平台 | **Windows first**，macOS/Linux 尽力而为 |

---

## Phase 1：Python 核心

**目标：** 后端核心逻辑可独立测试，不依赖 GUI。
**验收：** `pytest tests/` 全部通过。

---

### Task 1.1 — 创建项目骨架

**要创建的文件：**

```
foldermind/
├── core/__init__.py
├── core/types.py
├── tests/__init__.py
├── docs/spec.md
├── docs/contracts.md
├── docs/implementation-plan.md
├── requirements.txt
├── .gitignore
└── README.md
```

**`requirements.txt` 内容：**

```
pywebview==5.3.4
httpx==0.27.2
pathspec==0.12.1
keyring==25.4.1
pytest==8.3.3
```

**`core/types.py`：** 按 `docs/contracts.md` 的“Python 数据结构”章节完整实现 `ApiResult`、`ApiError`、`FileEntry`、`DuplicateGroup`、`ScanResult`、`Plan`、`Action`（含四个子类型）、`ActionResult`、`ExecuteResult`。

**运行命令：**

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest tests/ -v
```

**预期结果：** 没有测试，pytest 报 0 collected，正常退出。
**commit：** `chore: scaffold project structure`

---

### Task 1.2 — scanner.py + tests

**要创建的文件：** `core/scanner.py`、`tests/test_scanner.py`

**TDD 步骤：** 先写 `tests/test_scanner.py`，运行确认全部 FAILED，再实现 `core/scanner.py`。

**必须包含的测试用例：**

```python
# tests/test_scanner.py
import pytest
from pathlib import Path
from core.scanner import fast_scan, find_duplicates, smart_output

def test_basic_scan(tmp_path):
    (tmp_path / 'a.txt').write_text('hello')
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'b.txt').write_text('world')
    result = fast_scan(str(tmp_path), exclude_rules=[])
    assert result.file_count == 2
    paths = [f.relative_path for f in result.files]
    assert 'a.txt' in paths
    assert 'sub/b.txt' in paths

def test_excludes_git(tmp_path):
    (tmp_path / '.git').mkdir()
    (tmp_path / '.git' / 'config').write_text('git')
    (tmp_path / 'real.txt').write_text('real')
    result = fast_scan(str(tmp_path), exclude_rules=[])
    paths = [f.relative_path for f in result.files]
    assert not any('.git' in p for p in paths)
    assert 'real.txt' in paths

def test_excludes_node_modules(tmp_path):
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules' / 'pkg.js').write_text('js')
    (tmp_path / 'index.js').write_text('main')
    result = fast_scan(str(tmp_path), exclude_rules=[])
    paths = [f.relative_path for f in result.files]
    assert not any('node_modules' in p for p in paths)

def test_user_exclude_glob(tmp_path):
    (tmp_path / 'notes.tmp').write_text('temp')
    (tmp_path / 'doc.txt').write_text('doc')
    result = fast_scan(str(tmp_path), exclude_rules=['*.tmp'])
    paths = [f.relative_path for f in result.files]
    assert 'notes.tmp' not in paths
    assert 'doc.txt' in paths

def test_user_exclude_directory(tmp_path):
    cache = tmp_path / 'cache'
    cache.mkdir()
    (cache / 'data.bin').write_text('x')
    (tmp_path / 'main.py').write_text('py')
    result = fast_scan(str(tmp_path), exclude_rules=['cache/'])
    paths = [f.relative_path for f in result.files]
    assert not any('cache' in p for p in paths)

def test_duplicates_same_content(tmp_path):
    (tmp_path / 'a.txt').write_text('same content')
    (tmp_path / 'b.txt').write_text('same content')
    result = fast_scan(str(tmp_path), exclude_rules=[])
    dups = find_duplicates(result.files)
    assert len(dups) == 1
    assert len(dups[0].files) == 2

def test_duplicates_empty_file_excluded(tmp_path):
    (tmp_path / 'e1.txt').write_text('')
    (tmp_path / 'e2.txt').write_text('')
    result = fast_scan(str(tmp_path), exclude_rules=[])
    dups = find_duplicates(result.files)
    assert len(dups) == 0

def test_smart_output_small(tmp_path):
    for i in range(5):
        (tmp_path / f'f{i}.txt').write_text(f'c{i}')
    result = fast_scan(str(tmp_path), exclude_rules=[])
    out = smart_output(result, str(tmp_path), 'prompt {file_list}')
    assert out['action'] == 'send'
    assert '{file_list}' not in out['text']

def test_smart_output_warn(tmp_path):
    result = fast_scan(str(tmp_path), exclude_rules=[], _override_count=200)
    out = smart_output(result, str(tmp_path), 'prompt {file_list}')
    assert out['action'] == 'warn'

def test_smart_output_export(tmp_path):
    result = fast_scan(str(tmp_path), exclude_rules=[], _override_count=600)
    out = smart_output(result, str(tmp_path), 'prompt {file_list}')
    assert out['action'] == 'export'
```

**`core/scanner.py` 需实现的函数：**

```python
def fast_scan(path: str, exclude_rules: list, progress_callback=None, _override_count=None) -> ScanResult: ...
def find_duplicates(files: list) -> list: ...
def generate_tree(root_path: str, files: list) -> str: ...
def generate_for_ai(files: list) -> str: ...
def smart_output(scan_result, root_path: str, prompt_template: str) -> dict:
    # Returns: {'action': 'send'|'warn'|'export', 'text': str, 'export_path'?: str}
    ...
```

**运行：** `pytest tests/test_scanner.py -v` — 全部通过。
**commit：** `feat(scanner): implement file scanning with exclude rules and duplicate detection`

---

### Task 1.3 — executor.py + tests

**要创建的文件：** `core/executor.py`、`tests/test_executor.py`

**TDD 步骤：** 先写全部测试，确认全部 FAILED，再实现。

**必须包含的测试用例：**

```python
# tests/test_executor.py
import pytest, json
from core.executor import parse_json, execute_plan, undo_plan

SIMPLE_PLAN = json.dumps({'actions': [
    {'id': 1, 'type': 'create_dir', 'path': 'new_folder'},
    {'id': 2, 'type': 'move', 'from': 'a.txt', 'to': 'new_folder/a.txt'}
]})

def test_parse_json_valid():
    r = parse_json(SIMPLE_PLAN)
    assert r.ok
    assert len(r.data.actions) == 2

def test_parse_json_strips_markdown_fence():
    r = parse_json(f'```json\n{SIMPLE_PLAN}\n```')
    assert r.ok

def test_parse_json_invalid():
    r = parse_json('not json')
    assert not r.ok
    assert r.error.code == 'JSON_PARSE_ERROR'

def test_parse_json_rejects_absolute_path():
    bad = json.dumps({'actions': [{'id': 1, 'type': 'move', 'from': '/etc/passwd', 'to': 'out.txt'}]})
    r = parse_json(bad)
    assert not r.ok
    assert r.error.code == 'ABSOLUTE_PATH_NOT_ALLOWED'

def test_parse_json_rejects_traversal():
    bad = json.dumps({'actions': [{'id': 1, 'type': 'move', 'from': '../../secret', 'to': 'out'}]})
    r = parse_json(bad)
    assert not r.ok
    assert r.error.code == 'PATH_TRAVERSAL'

def test_create_dir(tmp_path):
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'create_dir', 'path': 'new'}]})).data
    r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert r.success_count == 1
    assert (tmp_path / 'new').is_dir()

def test_create_dir_existing_dir_ok(tmp_path):
    (tmp_path / 'existing').mkdir()
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'create_dir', 'path': 'existing'}]})).data
    r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert r.success_count == 1

def test_create_dir_target_is_file(tmp_path):
    (tmp_path / 'afile').write_text('content')
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'create_dir', 'path': 'afile'}]})).data
    r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert r.error_count == 1

def test_move_success(tmp_path):
    (tmp_path / 'a.txt').write_text('hello')
    (tmp_path / 'dest').mkdir()
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'move', 'from': 'a.txt', 'to': 'dest/a.txt'}]})).data
    r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert r.success_count == 1
    assert (tmp_path / 'dest' / 'a.txt').exists()
    assert not (tmp_path / 'a.txt').exists()

def test_move_source_missing(tmp_path):
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'move', 'from': 'missing.txt', 'to': 'dest/missing.txt'}]})).data
    r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert r.error_count == 1

def test_move_parent_dir_missing(tmp_path):
    (tmp_path / 'a.txt').write_text('hello')
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'move', 'from': 'a.txt', 'to': 'no_dir/a.txt'}]})).data
    r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert r.error_count == 1
    assert 'PARENT_DIR_NOT_FOUND' in r.results[0].message

def test_move_conflict_auto_rename(tmp_path):
    (tmp_path / 'a.txt').write_text('src')
    (tmp_path / 'dest').mkdir()
    (tmp_path / 'dest' / 'a.txt').write_text('existing')
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'move', 'from': 'a.txt', 'to': 'dest/a.txt'}]})).data
    r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert r.success_count == 1
    assert (tmp_path / 'dest' / 'a (1).txt').exists()

def test_move_conflict_skip(tmp_path):
    (tmp_path / 'a.txt').write_text('src')
    (tmp_path / 'dest').mkdir()
    (tmp_path / 'dest' / 'a.txt').write_text('existing')
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'move', 'from': 'a.txt', 'to': 'dest/a.txt'}]})).data
    r = execute_plan(str(tmp_path), plan, 'skip')
    assert r.skipped_count == 1
    assert (tmp_path / 'a.txt').exists()

def test_rename_success(tmp_path):
    (tmp_path / 'old.txt').write_text('content')
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'rename', 'path': '.', 'from': 'old.txt', 'to': 'new.txt'}]})).data
    r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert r.success_count == 1
    assert (tmp_path / 'new.txt').exists()

def test_delete_dir_empty(tmp_path):
    (tmp_path / 'empty').mkdir()
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'delete_dir', 'path': 'empty'}]})).data
    r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert r.success_count == 1
    assert not (tmp_path / 'empty').exists()

def test_delete_dir_with_ds_store(tmp_path):
    d = tmp_path / 'almost_empty'
    d.mkdir()
    (d / '.DS_Store').write_text('mac')
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'delete_dir', 'path': 'almost_empty'}]})).data
    r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert r.success_count == 1

def test_delete_dir_not_empty(tmp_path):
    d = tmp_path / 'full'
    d.mkdir()
    (d / 'file.txt').write_text('content')
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'delete_dir', 'path': 'full'}]})).data
    r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert r.error_count == 1

def test_undo_symmetry(tmp_path):
    (tmp_path / 'a.txt').write_text('hello')
    (tmp_path / 'dest').mkdir()
    plan = parse_json(json.dumps({'actions': [{'id': 1, 'type': 'move', 'from': 'a.txt', 'to': 'dest/a.txt'}]})).data
    exec_r = execute_plan(str(tmp_path), plan, 'auto_rename')
    assert exec_r.success_count == 1
    assert exec_r.undo_available
    undo_r = undo_plan(str(tmp_path), exec_r)
    assert undo_r.restored_count == 1
    assert (tmp_path / 'a.txt').exists()
    assert not (tmp_path / 'dest' / 'a.txt').exists()
```

**`core/executor.py` 需实现：**

```python
def parse_json(json_text: str) -> ApiResult: ...
def validate_actions(root_path: str, plan, conflict_policy: str) -> dict: ...
def preview_actions(root_path: str, plan) -> dict: ...
def execute_plan(root_path: str, plan, conflict_policy: str) -> ExecuteResult: ...
def undo_plan(root_path: str, exec_result: ExecuteResult) -> object: ...
def _auto_rename(target) -> object: ...  # file.txt -> file (1).txt
```

**运行：** `pytest tests/test_executor.py -v` — 全部通过。
**commit：** `feat(executor): implement plan execution with conflict handling and undo`

---

### Task 1.4 — config.py + tests

**要创建的文件：** `core/config.py`、`tests/test_config.py`

**必须包含的测试：**

```python
# tests/test_config.py
import json, pytest
from core.config import load_config, save_config, get_api_key, set_api_key

def test_load_default_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    config = load_config()
    assert config.provider == 'anthropic'
    assert config.conflict_policy == 'ask'
    assert config.config_version == 1

def test_save_and_reload(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    config = load_config()
    config.theme = 'light'
    save_config(config)
    loaded = load_config()
    assert loaded.theme == 'light'

def test_no_api_key_in_file(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    config = load_config()
    save_config(config)
    raw = json.loads((tmp_path / '.foldermind_config.json').read_text())
    assert 'api_key' not in str(raw).lower()

def test_migration_adds_missing_fields(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    old = {'config_version': 0, 'provider': 'openai'}
    (tmp_path / '.foldermind_config.json').write_text(json.dumps(old))
    config = load_config()
    assert config.config_version == 1
    assert hasattr(config, 'conflict_policy')

def test_memory_mode(monkeypatch):
    set_api_key('anthropic', 'sk-test', memory_only=True)
    assert get_api_key('anthropic', memory_only=True) == 'sk-test'
```

**运行：** `pytest tests/test_config.py -v`
**commit：** `feat(config): implement config persistence and keyring API key storage`

---

### Task 1.5 — prompts.py

**要创建的文件：** `core/prompts.py`

**内容：** 5 个内置预设 + `list_prompts`、`save_prompt`、`delete_prompt`函数。
预设提示词末尾必须包含强制规则：统一用 `/` 路径、不编造文件名、不删除文件、只输出 JSON。

**commit：** `feat(prompts): implement preset prompt management`

---

## Phase 2：pywebview 桥接

**目标：** 前端可以通过 `pywebview.api` 调用后端。
**验收：** `python main_gui.py --dev` 启动窗口；在 DevTools 控制台调用 `pywebview.api.load_config()` 得到 `{ok: true, data: {...}}`。

---

### Task 2.1 — main_gui.py + Api 类

**要创建的文件：** `main_gui.py`、`core/web_api.py`

**`core/web_api.py` 中 `Api` 类必须实现以下全部方法，全部按 contracts.md 返回 `ApiResult.to_dict()`：**

```python
class Api:
    def scan_folder(self, path: str) -> dict: ...
    def generate_plan(self, input: dict) -> dict: ...
    def parse_plan(self, json_text: str) -> dict: ...
    def preview_plan(self, root_path: str, plan: dict) -> dict: ...
    def execute_plan(self, root_path: str, plan: dict, conflict_policy: str) -> dict: ...
    def undo_last(self) -> dict: ...
    def load_config(self) -> dict: ...
    def save_config(self, config: dict) -> dict: ...
    def test_connection(self, input: dict) -> dict: ...
    def list_prompts(self) -> dict: ...
    def save_prompt(self, prompt: dict) -> dict: ...
    def delete_prompt(self, key: str) -> dict: ...
    # AI plan generation is exposed only through generate_plan.
```

**commit：** `feat(bridge): implement pywebview API bridge`

---

## Phase 3：Svelte UI MVP

**目标：** 能完整走通整理主流程（选路径 → 扫描 → 选提示词 → 粘贴 JSON → 预览 → 执行 → 撤销）。
**验收：** 不用真实 AI，手动粘贴 JSON 能完整走通一次文件整理操作。

---

### Task 3.1 — 前端骨架

**要创建的文件：**

```
frontend/
├── src/
│   ├── App.svelte              使用侧边栏 + 路由
│   ├── main.ts
│   ├── app.css                 CSS 变量、主题、全局样式
│   ├── lib/
│   │   ├── api.ts              封装 pywebview.api 调用
│   │   ├── types.ts            直接按 contracts.md 实现 TS 类型
│   │   └── stores.ts           全局 store + window.__emit 初始化
│   └── pages/
│       ├── Organize.svelte
│       └── Settings.svelte
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── svelte.config.js
```

**`lib/stores.ts` 必须初始化 `window.__emit`，处理 `scan.progress`、`scan.done`、`scan.error`、`ai.chunk`、`ai.done`、`ai.error` 事件。**

**commit：** `feat(frontend): scaffold Svelte 5 frontend`

---

### Task 3.2 — 整理页主流程（每步一个 commit）

1. **路径输入 + 选择按鈕**
   - 文件夹选择对话框（`webview.windows[0].create_file_dialog`）
   - 路径非空时扫描按鈕解锁
   - **commit：** `feat(organize): path selection + scan`

2. **扫描 + 文件树展示**
   - 调用 `api.scan_folder`，监听 `scan.progress` 进度
   - `scan.done` 后渲染 `FileTree.svelte`
   - **commit：** `feat(organize): file tree display`

3. **提示词芯片选择 + 整理要求输入**
   - 调用 `api.list_prompts()` 加载提示词列表
   - 单击选中预设提示词，右侧提供自然语言整理要求输入框
   - **commit：** `feat(organize): prompt selection and instruction input`

4. **调用 AI 生成整理方案**
   - 调用 `api.generate_plan`，将文件清单、用户整理要求、提示词、provider 和 model 发送给后端
   - textarea 监听 `ai.chunk` 事件实时追加 AI 流式输出；`ai.done` 后自动调用 `api.parse_plan`
   - 失败时显示可读错误，并允许用户修改要求后重新生成
   - **commit：** `feat(organize): generate AI plan`

5. **导入/粘贴 JSON + 解析（备用入口）**
   - textarea 支持粘贴；支持拖入 `.json` 文件（HTML5 drag-drop）
   - 输入后调用 `api.parse_plan`，失败显示错误，成功解锁预览
   - **commit：** `feat(organize): JSON import and parse fallback`

6. **预览弹窗 + 执行**
   - 点击预览调用 `api.preview_plan`，`PreviewModal.svelte` 展示操作列表、冲突、缺失路径警告
   - 确认后调用 `api.execute_plan`，完成后弹出 `ResultModal.svelte`
   - **commit：** `feat(organize): preview and execute`

7. **撤销**
   - 执行成功且 `undoAvailable` 为 true 时，底部撤销按鈕解锁
   - 点击调用 `api.undo_last()`
   - **commit：** `feat(organize): undo`

---

### Task 3.3 — 设置页

**实现内容：** AI 服务商分段控件、模型列表、自定义 Endpoint、API Key 输入框、测试连接、冲突处理策略单选、排除规则 textarea。
**commit：** `feat(settings): implement settings page`

---

### Task 3.4 — 冲突弹窗（ask 策略）

**`ConflictModal.svelte`：** 展示冲突详情（源/目标路径），提供“重命名”和“跳过”（**不含覆盖**），“应用到剩余所有冲突”复选框。
**commit：** `feat(conflict): implement conflict resolution modal`

---

## Phase 4：AI API 接入

**目标：** 支持真实 AI 调用，textarea 能实时显示流式输出。
**验收：** 配置真实 API Key 后能发送 prompt，textarea 实时追加 chunk，请求失败能显示可读错误。

---

### Task 4.1 — api.py 流式 AI 调用

**要创建的文件：** `core/api.py`

**需实现：**

```python
def send_to_ai(prompt, config, api_key, on_chunk, on_success, on_error): ...
# - 在后台线程运行，不阻塞主线程
# - 默认走 SSE 流式接口（stream: true）
# - 指数退避重试：1s / 2s / 4s，最多 3 次
# - 429 时优先遵守 Retry-After header
# Anthropic header: x-api-key + anthropic-version: 2023-06-01
# OpenAI header: Authorization: Bearer {key}

def test_connection(input) -> ApiResult: ...
# max_tokens=8 的最小请求，超时 15 秒
```

**commit：** `feat(api): implement streaming AI API with retry`

---

### Task 4.2 — 前端接入流式响应

**修改 `Organize.svelte`：**
- “发送给 AI”按鈕实际调用 AI，textarea 监听 `ai.chunk` 事件实时追加
- `ai.done` 时自动触发 `api.parse_plan`
- `ai.error` 时显示错误状态

**修改 `core/web_api.py`：** `send_to_ai` 通过 `window.evaluate_js` 调用 `window.__emit('ai.chunk', chunk)` 等。

**commit：** `feat(frontend): wire up streaming AI response to textarea`

---

## Phase 5：增强功能

**目标：** 补齐完整 v1 体验，每项独立实现，互不依赖。**

---

### Task 5.1 — 历史页 + 持久化撤销

**要创建/修改：** `core/logger.py`、`frontend/src/pages/History.svelte`

历史页布局：
- 顶部搜索框（实时过滤路径/提示词名称）
- 状态过滤下拉菜单（全部 / 仅成功 / 含错误 / 已撤销）
- 清空历史按鈕（二次确认）
- 卡片列表：路径、时间、提示词名称、AI 服务商和模型、成功/跳过/错误统计、撤销/删除按鈕

**commit：** `feat(history): implement history page with persistent undo`

---

### Task 5.2 — Windows 原生拖放

**要创建的文件：** `core/dragdrop_win.py`

实现要点：
- `register(hwnd, webview_win)`：调用 `DragAcceptFiles`，子类化 `WM_DROPFILES` 消息处理
- `_wndproc_ref` 必须保存在模块级变量，防止 GC 回收导致崩溃
- 拖入文件夹直接用该路径；拖入文件取其父目录
- `FindWindowW` 失败时降级处理（禁用拖放但不崩溃）
- `main_gui.py` 在 `shown` 事件中，`sys.platform == 'win32'` 时调用 `register`

**commit：** `feat(dragdrop): implement Windows native file drag-drop`

---

### Task 5.3 — 多语言 i18n

**要创建的文件：** `core/i18n.ts`、`locales/zh-CN.json`、`locales/en.json`

实现方式：
- `lang` store + `loadLang(l)` 异步加载 + `t` derived store
- `$t('key')` 语法，store 变更自动重渲染，无需重启
- 语言偏好同步写入 config（`api.save_config`）

**commit：** `feat(i18n): implement Chinese/English language switching`

---

### Task 5.4 — PyInstaller 打包

**要创建的文件：** `build.spec`

```bash
# 构建流程
cd frontend && pnpm build
cd .. && pyinstaller build.spec
```

**关键 spec 配置（Windows）：** `--collect-all webview`、`--add-data 'ui/dist:ui/dist'`、图标、版本号、产品元信息。
**验收：** 打包产物能独立运行，不依赖 Python 环境。
**commit：** `chore(build): add PyInstaller build spec`

---

### Task 5.5 — GitHub Actions CI

**要创建的文件：** `.github/workflows/test.yml`

```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v
```

**commit：** `ci: add GitHub Actions test workflow`

---

## 推荐 commit 序列

```
chore: scaffold project structure
feat(scanner): implement file scanning with exclude rules and duplicate detection
feat(executor): implement plan execution with conflict handling and undo
feat(config): implement config persistence and keyring API key storage
feat(prompts): implement preset prompt management
feat(bridge): implement pywebview API bridge
feat(frontend): scaffold Svelte 5 frontend
feat(organize): path selection + scan
feat(organize): file tree display
feat(organize): prompt selection and instruction input
feat(organize): generate AI plan
feat(organize): JSON import and parse fallback
feat(organize): preview and execute
feat(organize): undo
feat(settings): implement settings page
feat(conflict): implement conflict resolution modal
--- MVP 完成 ---
feat(api): implement streaming AI API with retry
feat(frontend): wire up streaming AI response to textarea
--- Phase 4 完成 ---
feat(history): implement history page with persistent undo
feat(dragdrop): implement Windows native file drag-drop
feat(i18n): implement Chinese/English language switching
chore(build): add PyInstaller build spec
ci: add GitHub Actions test workflow
--- v1 完成 ---
```
