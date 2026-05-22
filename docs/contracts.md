# FolderMind — 接口与数据契约（contracts.md）

> 本文档描述"模块之间如何通信"。  
> 产品功能说明见 `docs/spec.md`；实现步骤见 `docs/implementation-plan.md`。  
> **当 spec.md 与本文档冲突时，以本文档为准。**

---

## 约定

- 所有 pywebview API 方法均返回 `ApiResult<T>` 结构，不直接抛出 Python 异常文本
- AI JSON 中所有路径必须是相对根目录的路径，使用 `/` 作为分隔符，禁止绝对路径和 `..` 穿越
- 后端执行前将路径转换为 `Path` 并调用 `.resolve()`，确认仍在根目录内
- MVP 不支持覆盖文件，`ask` 策略冲突弹窗只提供"重命名"和"跳过"，不含"覆盖"

---

## 统一返回结构

### TypeScript

```ts
type ApiResult<T> = {
  ok: boolean;
  data?: T;
  error?: ApiError;
};

type ApiError = {
  code: ErrorCode;      // 见"错误码"章节
  message: string;      // 人类可读的错误描述
  details?: unknown;    // 可选补充信息（路径、字段名等）
};
```

### Python（`core/types.py`）

```python
from dataclasses import dataclass, field
from typing import TypeVar, Generic, Optional, Any

T = TypeVar("T")

@dataclass
class ApiError:
    code: str
    message: str
    details: Optional[Any] = None

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.details is not None:
            d["details"] = self.details
        return d

@dataclass
class ApiResult(Generic[T]):
    ok: bool
    data: Optional[T] = None
    error: Optional[ApiError] = None

    def to_dict(self) -> dict:
        d: dict = {"ok": self.ok}
        if self.data is not None:
            d["data"] = self.data if isinstance(self.data, dict) else self.data
        if self.error is not None:
            d["error"] = self.error.to_dict()
        return d

    @staticmethod
    def success(data: T) -> "ApiResult[T]":
        return ApiResult(ok=True, data=data)

    @staticmethod
    def fail(code: str, message: str, details: Any = None) -> "ApiResult":
        return ApiResult(ok=False, error=ApiError(code=code, message=message, details=details))
```

---

## pywebview API 契约

前端通过 `pywebview.api.方法名()` 调用，Python `Api` 类在 `main_gui.py` 中通过 `js_api=Api()` 注册。
前端在 `frontend/src/lib/api.ts` 中封装为带 TypeScript 类型的 Promise。

```ts
// frontend/src/lib/api.ts — 所有方法签名

scan_folder(path: string): Promise<ApiResult<ScanResult>>;

// AI 整理方案生成（单次请求模式，无 general chat API）
generate_plan(input: GeneratePlanInput): Promise<ApiResult<Plan>>;

// 本地校验 + 计算整理后树状图
preview_plan(rootPath: string, plan: Plan): Promise<ApiResult<PreviewResult>>;

// 执行整理操作
execute_plan(
  rootPath: string,
  plan: Plan,
  conflictPolicy: ConflictPolicy
): Promise<ApiResult<ExecuteResult>>;

// JSON 解析和 schema 校验（导入 JSON 备用流程使用）
parse_plan(jsonText: string): Promise<ApiResult<Plan>>;

undo_last(): Promise<ApiResult<UndoResult>>;

load_config(): Promise<ApiResult<Config>>;

save_config(config: Config): Promise<ApiResult<void>>;

test_connection(input: ConnectionTestInput): Promise<ApiResult<ConnectionTestResult>>;

// 提示词管理
list_prompts(): Promise<ApiResult<PromptItem[]>>;
save_prompt(prompt: PromptItem): Promise<ApiResult<PromptItem>>;
delete_prompt(key: string): Promise<ApiResult<void>>;
```

---

## 核心数据类型

### TypeScript（`frontend/src/lib/types.ts`）

```ts
// ---- 文件扫描 ----

type FileEntry = {
  relativePath: string;   // 相对根目录的路径，使用 / 分隔
  absolutePath: string;
  name: string;           // 文件名（不含路径）
  size: number;           // 字节数
  modifiedTime: string;   // ISO 8601 格式，如 "2024-03-15T10:30:00"
  isDir: boolean;
};

type DuplicateGroup = {
  hash: string;           // SHA1
  files: FileEntry[];
};

type ScanResult = {
  rootPath: string;
  files: FileEntry[];
  treeText: string;       // 树状目录字符串，用于展示
  duplicates: DuplicateGroup[];
  warnings: string[];     // 大文件夹警告、超阈值警告等
  fileCount: number;      // 总文件数（不含目录）
};

// ---- 提示词 ----

type PromptItem = {
  key: string;            // 唯一键，预设用固定字符串，自定义用 uuid
  name: string;
  content: string;
  isPreset: boolean;
  isDeleted?: boolean;    // 用户删除的预设，记录在 config 中
};

type PromptResult = {
  promptText: string;     // 完整的发给 AI 的内容（提示词 + 文件清单）
  fileCount: number;
  exportedFilePath?: string; // 文件数 > 500 时，导出的 .md 文件路径
};

// ---- 整理方案 ----

type GeneratePlanInput = {
  rootPath: string;
  fileListForAi: string;      // generate_for_ai() 生成的纯文本清单
  userInstruction: string;    // 用户输入的自然语言整理要求
  promptKey?: string;          // 选中的预设提示词 key（可选）
  provider: Provider;
  model: string;
};

type Plan = {
  summary?: string;
  actions: Action[];
};

type Action =
  | CreateDirAction
  | MoveAction
  | RenameAction
  | DeleteDirAction;

type CreateDirAction = {
  id: number;
  type: "create_dir";
  path: string;           // 相对根目录的目标目录路径
  reason?: string;
};

type MoveAction = {
  id: number;
  type: "move";
  from: string;           // 相对路径，指向文件
  to: string;             // 相对路径，指向文件
  reason?: string;
};

type RenameAction = {
  id: number;
  type: "rename";
  path: string;           // 所在目录的相对路径
  from: string;           // 旧文件名（不含路径）
  to: string;             // 新文件名（不含路径）
  reason?: string;
};

type DeleteDirAction = {
  id: number;
  type: "delete_dir";
  path: string;           // 相对路径，指向目录
  reason?: string;
};

// ---- 预览 ----

type PreviewResult = {
  beforeTreeText: string;  // 整理前文件树字符串（供左侧展示）
  afterTreeText: string;   // 整理后文件树字符串（本地计算，供右侧展示）
  lines: PreviewLine[];    // 每条操作的可读描述
  conflicts: ConflictItem[];
  missingPaths: string[];  // from 路径不存在的警告
};

type PreviewLine = {
  actionId: number;
  description: string;    // 人类可读，如 "移动 文件.pdf → 新文件夹/文件.pdf"
  hasConflict: boolean;
};

type ConflictItem = {
  actionId: number;
  type: "move" | "rename";
  sourcePath: string;
  targetPath: string;
  resolution?: ConflictResolution; // auto_rename 策略时预先填入
};

// ---- 执行 ----

type ConflictPolicy = "ask" | "auto_rename" | "skip";

type ConflictResolution = "rename" | "skip";  // MVP 不含 overwrite

type ActionStatus = "success" | "skipped" | "error";

type ActionResult = {
  actionId: number;
  status: ActionStatus;
  message: string;
  finalPath?: string;     // move/rename 成功时，实际落地路径（auto_rename 时可能不同于原 to）
};

type ExecuteResult = {
  results: ActionResult[];
  successCount: number;
  skippedCount: number;
  errorCount: number;
  undoAvailable: boolean;
};

type UndoResult = {
  restoredCount: number;
  skippedCount: number;   // 因外部改动无法恢复的
  details: ActionResult[];
};

type UndoAction = {
  type: "move" | "rename" | "delete_dir_restore" | "remove_dir"; // 原操作的逆操作类型
  originalActionId: number;
  from: string;           // 撤销时的源路径
  to?: string;            // 撤销时的目标路径（move/rename 用）
};

// ---- 配置 ----

type Provider = "anthropic" | "openai" | "custom";

type Config = {
  provider: Provider;
  providerModels: Record<Provider, string>;      // 每个服务商当前选中的模型
  customModels: Record<Provider, string[]>;       // 用户追加的自定义模型
  customEndpointUrl: string;
  conflictPolicy: ConflictPolicy;
  excludeRules: string[];                          // gitignore 风格的 glob，每行一条
  language: "zh-CN" | "en";
  theme: "dark" | "light";
  configVersion: number;                           // 初版为 1
  deletedPresetKeys: string[];                     // 用户删除的预设提示词的 key
  customPrompts: PromptItem[];
  historyRetentionLimit: number;                  // 默认 100
  saveUnexecutedAiPlans: boolean;                 // 默认 false：未执行 AI 方案不保存完整 actions
  saveRawAiResponses: boolean;                    // 默认 false：不保存 AI 原始完整响应文本
};

// ---- AI 连接测试 ----

type ConnectionTestInput = {
  provider: Provider;
  model: string;
  apiKey: string;
  customUrl?: string;
};

type ConnectionTestResult = {
  success: boolean;
  latencyMs?: number;
  errorMessage?: string;
};

// ---- 历史记录（Phase 5）----

type AiGenerationStatus = "generated" | "failed" | "executed" | "discarded";

type AiGenerationRecord = {
  id: string;
  type: "ai_generation";
  rootPath: string;
  createdAt: string;             // ISO 8601
  provider: Provider;
  model: string;
  promptKey?: string;
  promptName?: string;
  userInstruction: string;
  summary?: string;
  actionCount: number;
  status: AiGenerationStatus;
  executionId?: string;          // 关联的 ExecutionRecord.id
  errorMessage?: string;
  // 注意：actions（完整 JSON）默认不保存（未执行时）
  // 原始 AI 响应文本默认不保存（避免历史文件过大）
};

type UndoStatus = "available" | "undone" | "unavailable";

type ExecutionRecord = {
  id: string;
  type: "execution";
  rootPath: string;
  createdAt: string;             // ISO 8601
  source: "ai_generated" | "manual_json";
  sourceGenerationId?: string;   // 关联的 AiGenerationRecord.id
  provider?: Provider;
  model?: string;
  promptKey?: string;
  promptName?: string;
  userInstruction?: string;
  summary?: string;
  successCount: number;
  skippedCount: number;
  errorCount: number;
  actions: Action[];             // 必须保存（执行过的完整方案）
  results: ActionResult[];       // 必须保存（每条操作的执行结果）
  undoStack: UndoAction[];       // 必须保存（用于重启后撤销）
  undoStatus: UndoStatus;
};
```

### Python 数据结构（`core/types.py`，与 TS 类型一一对应）

```python
from dataclasses import dataclass, field
from typing import Literal, Optional, Union

# ---- 文件扫描 ----

@dataclass
class FileEntry:
    relative_path: str
    absolute_path: str
    name: str
    size: int
    modified_time: str      # ISO 8601
    is_dir: bool

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

# ---- AI 生成输入 ----

@dataclass
class GeneratePlanInput:
    root_path: str
    file_list_for_ai: str      # generate_for_ai() 生成的纯文本清单
    user_instruction: str      # 用户输入的自然语言整理要求
    prompt_key: Optional[str] = None
    provider: str = "anthropic"
    model: str = ""

# ---- 整理方案 ----

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
    from_path: str          # JSON key "from"，Python 关键字冲突，内部用 from_path
    to: str
    reason: Optional[str] = None

@dataclass
class RenameAction:
    id: int
    type: Literal["rename"]
    path: str
    from_name: str          # JSON key "from"
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

# ---- 执行 ----

ActionStatus = Literal["success", "skipped", "error"]

@dataclass
class ActionResult:
    action_id: int
    status: ActionStatus
    message: str
    final_path: Optional[str] = None

@dataclass
class ExecuteResult:
    results: list[ActionResult]
    success_count: int
    skipped_count: int
    error_count: int
    undo_available: bool

ConflictPolicy = Literal["ask", "auto_rename", "skip"]
```

---

## AI 返回 JSON Schema

AI 必须严格返回以下格式，提示词末尾的强制规则已约束此输出。

```json
{
  "summary": "整理思路（可选，一句话）",
  "actions": [
    { "id": 1, "type": "create_dir", "path": "新文件夹", "reason": "..." },
    { "id": 2, "type": "move", "from": "原路径/文件.pdf", "to": "新路径/文件.pdf", "reason": "..." },
    { "id": 3, "type": "rename", "path": "所在目录", "from": "旧名.jpg", "to": "新名.jpg", "reason": "..." },
    { "id": 4, "type": "delete_dir", "path": "要删除的空文件夹", "reason": "..." }
  ]
}
```

**验证规则：**
- `actions` 必填，必须是数组
- 每个 action 必须有 `id`（整数）、`type`（四种之一）和必要字段
- 所有路径必须是相对路径，禁止 `/`、`C:\` 等绝对路径开头
- 所有路径禁止包含 `..` 片段
- 路径分隔符统一用 `/`
- `reason` 字段可选

---

## 错误码

```ts
type ErrorCode =
  | "INVALID_PATH"              // 路径为空、非法或不存在
  | "PATH_TRAVERSAL"            // 路径试图跳出根目录
  | "ABSOLUTE_PATH_NOT_ALLOWED" // AI JSON 中出现绝对路径
  | "JSON_PARSE_ERROR"          // AI 返回内容不是合法 JSON
  | "INVALID_ACTION_SCHEMA"     // action 缺少必要字段或类型错误
  | "SOURCE_NOT_FOUND"          // move/rename 的源文件不存在
  | "TARGET_EXISTS"             // create_dir 目标是文件（非目录）
  | "PARENT_DIR_NOT_FOUND"      // move 时父目录不存在，要求 AI 先输出 create_dir
  | "DIRECTORY_NOT_EMPTY"       // 试图 delete_dir 非空目录
  | "API_KEY_MISSING"           // 未配置 API Key
  | "AI_REQUEST_FAILED"         // AI 请求失败（网络/认证/超限等）
  | "CONFIG_LOAD_FAILED"        // 配置读取失败
  | "CONFIG_SAVE_FAILED"        // 配置保存失败
  | "UNKNOWN_ERROR";            // 未分类错误
```

---

## 路径规则

| 规则 | 说明 |
|---|---|
| 相对路径 | AI JSON 中所有路径必须是相对根目录的路径 |
| 禁止绝对路径 | 禁止以 `/`、`C:\` 等开头的路径 |
| 禁止路径穿越 | 禁止包含 `..` 片段 |
| 统一分隔符 | AI JSON 和前端展示统一用 `/`；后端执行时根据 OS 转换 |
| 安全检查 | 后端执行前调用 `Path.resolve()` 并确认仍在根目录内 |
| move 只移文件 | `move.from` 和 `move.to` 都必须指向文件，不允许移动目录 |
| rename 只改文件名 | `rename` 只允许重命名文件，不允许重命名目录 |
| delete_dir 只删空目录 | 非空目录报错，不递归删除 |

---

## 执行规则

### create_dir

- 目标不存在时创建目录（递归创建所有缺失的父目录）
- 目标已存在且是目录时视为成功，不报错
- 目标已存在且是文件时返回错误 `TARGET_EXISTS`

### move

- 源文件不存在时返回错误 `SOURCE_NOT_FOUND`，跳过该操作，不中断整体执行
- **父目录不存在时返回错误 `PARENT_DIR_NOT_FOUND`**，不自动创建（要求 AI 先输出 `create_dir`）
- 目标已存在时按冲突策略处理（见冲突处理规则）
- 成功时 `finalPath` 返回实际落地路径（`auto_rename` 时可能不同于原 `to`）

### rename

- `path` 表示所在目录，`from` 是旧文件名，`to` 是新文件名
- 源文件不存在时返回 `SOURCE_NOT_FOUND`，跳过
- 目标已存在时按冲突策略处理

### delete_dir

- 删除前静默清理白名单系统垃圾文件（`.DS_Store` / `Thumbs.db` / `desktop.ini` / `.localized`）
- 清理后仍不为空时返回错误 `DIRECTORY_NOT_EMPTY`，跳过，不递归删除
- 目标不存在时视为成功（幂等）

### undo

- 当前会话内存 undo stack（MVP 不做持久化）
- 只有执行成功的操作才进入 undo stack
- 撤销按逆序执行（后执行的先撤销）
- 撤销 move → 执行反向 move（to → from）
- 撤销 rename → 执行反向 rename（to → from）
- 撤销 create_dir → 删除创建的目录（若目录已被外部修改则跳过并记录）
- 撤销 delete_dir → 重建目录（无法恢复内容，只重建空目录）
- 撤销遇到外部改动时跳过并在结果里显示，不中断整体撤销

---

## 冲突处理规则

**MVP 不支持覆盖文件。**

| 策略 | 行为 |
|---|---|
| `auto_rename` | 目标已存在时自动生成唯一名称 |
| `skip` | 目标已存在时跳过该条操作，记录为 `skipped` |
| `ask` | 弹窗询问用户，逐条或批量选择"重命名"或"跳过" |

**`auto_rename` 命名规则：**

```
file.txt       → file (1).txt
file (1).txt   → file (2).txt  （若 (1) 已存在）
README         → README (1)    （无扩展名）
```

递增数字直到找到不冲突的名称为止。

---

## 配置文件结构

路径：`~/.foldermind_config.json`

```json
{
  "config_version": 1,
  "provider": "anthropic",
  "provider_models": {
    "anthropic": "claude-opus-4-6",
    "openai": "gpt-4o",
    "custom": ""
  },
  "custom_models": {
    "anthropic": [],
    "openai": [],
    "custom": []
  },
  "custom_endpoint_url": "",
  "conflict_policy": "ask",
  "exclude_rules": [],
  "language": "zh-CN",
  "theme": "dark",
  "deleted_preset_keys": [],
  "custom_prompts": [],
  "history_retention_limit": 100,
  "save_unexecuted_ai_plans": false,
  "save_raw_ai_responses": false
}
```

**注意：** 文件不含 `api_key` 字段，API Key 存于操作系统密钥环。

**配置迁移：** 读取时检查 `config_version`，低于当前版本时执行迁移函数补全缺失字段，迁移后写回。

---

## 日志/历史文件结构

路径：`~/.foldermind_logs/{timestamp}.json`（Phase 5 增强功能，MVP 不实现）

```json
{
  "timestamp": "2024-03-15T10:30:00",
  "root_path": "C:/Users/xxx/Documents",
  "prompt_key": "organize",
  "provider": "anthropic",
  "model": "claude-opus-4-6",
  "success_count": 12,
  "skipped_count": 1,
  "error_count": 0,
  "results": [ ],
  "undo_stack": [ ]
}
```

---

## 历史记录文件结构（Phase 5）

路径：`~/.foldermind_logs/{timestamp}_{type}.json`

每次执行产生一个 `ExecutionRecord` JSON 文件；
每次调用 AI 生成（不论是否执行）产生一个 `AiGenerationRecord` JSON 文件。
两者通过 `id` / `sourceGenerationId` / `executionId` 字段关联。

**保存策略：**

| 内容 | 是否保存 | 说明 |
|---|---|---|
| 执行过的 actions | **必须** | 用于历史查看和审计 |
| 每条 action 的 result | **必须** | 成功/跳过/错误详情 |
| undoStack | **必须** | 用于重启后撤销 |
| AI 生成的摘要和操作数 | 是 | 轻量元信息 |
| 未执行方案的完整 actions | **默认否** | 设置可开启 |
| AI 原始响应文本 | **默认否** | 设置可开启，避免文件过大 |

**最大历史条数：** 默认 100，可在设置中修改。

---

## 前端推送事件（Backend → Frontend）

Python 后端通过 `webview.windows[0].evaluate_js()` 调用前端的 `window.__emit(event, payload)`。

| 事件名 | Payload 类型 | 说明 |
|---|---|---|
| `scan.progress` | `number`（0–100） | 扫描进度百分比 |
| `scan.done` | `ScanResult` | 扫描完成，返回完整结果 |
| `scan.error` | `ApiError` | 扫描失败 |
| `ai.chunk` | `string` | AI 流式响应的增量内容 |
| `ai.done` | `string` | AI 响应完成，返回完整内容 |
| `ai.error` | `ApiError` | AI 请求失败 |
| `dragdrop.folder` | `string` | Windows 拖放：文件所在目录路径（Phase 5） |

前端在 `frontend/src/lib/stores.ts` 初始化段挂载：

```ts
window.__emit = (event: string, payload: unknown) => {
    // 分发到对应 store
};
```

---

## UI 状态规则

| 按钮/控件 | 启用条件 |
|---|---|
| 扫描 | 路径输入框非空 |
| 发送给 AI | 扫描已完成 && 已选择提示词 |
| 预览 | JSON 已解析成功 |
| 执行整理 | 预览通过（未取消预览弹窗）|
| 撤销 | 上次执行完成 && undo stack 非空 |

**扫描中：** 路径输入、选择按钮、扫描按钮全部 disabled；扫描失败时显示错误，不清空上次成功结果。

**执行中：** 执行按钮 disabled，禁止重复点击；每条操作产生 success/skipped/error 结果；执行完成后弹出结果弹窗。

**JSON 格式错误时：** 显示解析错误，预览和执行按钮保持 disabled。

---

## 项目目录结构

```
foldermind/
├── core/
│   ├── types.py            ApiResult、ApiError、FileEntry、Plan、Action 等数据类
│   ├── scanner.py          文件扫描、树状图、重复检测、排除规则
│   ├── executor.py         JSON 解析、执行操作、冲突处理、undo stack
│   ├── prompts.py          预设提示词管理
│   ├── config.py           配置持久化、API Key 密钥环存储
│   ├── logger.py           执行日志（Phase 5）
│   ├── api.py              AI API 调用（流式 + 重试）（Phase 4）
│   └── dragdrop_win.py     Windows 原生拖放（Phase 5）
├── frontend/
│   ├── src/
│   │   ├── App.svelte
│   │   ├── main.ts
│   │   ├── app.css
│   │   ├── lib/
│   │   │   ├── api.ts      封装 pywebview.api 调用
│   │   │   ├── stores.ts   全局 store + window.__emit
│   │   │   ├── types.ts    TypeScript 类型（与本文档保持一致）
│   │   │   └── i18n.ts     国际化（Phase 5）
│   │   ├── pages/
│   │   │   ├── Organize.svelte
│   │   │   ├── History.svelte  （Phase 5）
│   │   │   └── Settings.svelte
│   │   ├── components/
│   │   │   ├── FileTree.svelte
│   │   │   ├── PromptChip.svelte
│   │   │   ├── PreviewModal.svelte
│   │   │   ├── ConflictModal.svelte
│   │   │   └── ResultModal.svelte
│   │   └── locales/        （Phase 5）
│   └── ...
├── ui/dist/                Vite 构建产物
├── tests/
│   ├── test_scanner.py
│   ├── test_executor.py
│   └── test_config.py
├── docs/
│   ├── spec.md
│   ├── contracts.md
│   └── implementation-plan.md
├── main_gui.py
├── requirements.txt
└── build.spec
```
