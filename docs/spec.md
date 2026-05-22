# FolderMind — 产品规格文档（spec.md）

> 本文档描述"要做什么"和"为什么这样做"。  
> 接口和数据格式见 `docs/contracts.md`；实现步骤见 `docs/implementation-plan.md`。

---

## 项目概述

FolderMind 是一个 AI 驱动的**本地文件夹整理桌面工具**，带有图形界面。

核心流程：
1. 用户选择一个文件夹
2. 程序扫描文件并生成结构化清单
3. 清单发送给 AI（Claude、GPT 或自定义模型）
4. AI 返回 JSON 格式的整理方案
5. 程序解析方案并展示预览，用户确认后执行（移动、重命名、新建/删除文件夹）
6. 支持一键撤销所有操作

整个流程**完全在本地运行**，文件不上传到任何服务器，AI 调用只传递文件名和修改时间，不传递文件内容。

---

## 用户目标

- 以最少的手动操作，把混乱的文件夹整理成有清晰结构的目录
- 能在执行前看到完整预览，不怕改错
- 出错时可以一键撤销，不留残局
- 不依赖云服务，不担心文件隐私

---

## 技术栈

| 层级 | 技术 | 版本 | 说明 |
|---|---|---|---|
| 后端语言 | Python | 3.12.x | 主语言，虚拟环境隔离 |
| GUI 容器 | pywebview | 5.x | 用系统内置 WebView 渲染前端，无需打包 Chromium |
| 前端框架 | Svelte | 5.x | 组件化、响应式、编译产物极小 |
| 前端构建 | Vite | 当前稳定版 | 开发热重载，生产打包到 `ui/dist/` |
| 前端包管理 | pnpm | 9.x 或 10.x | 比 npm 快、磁盘占用低 |
| AI 调用 | httpx | 0.27.x | 支持 SSE 流式响应、连接池、超时控制 |
| 路径匹配 | pathspec | 0.12.x | 解析 gitignore 风格的排除规则 |
| 凭据存储 | keyring | 25.x | API Key 持久化到操作系统密钥环 |
| 测试 | pytest | 8.x | 单元测试 |
| 运行时 Node | Node.js | 20 LTS（最低 18） | 前端构建工具运行环境 |

**选型理由：** Svelte 无虚拟 DOM、产物体积最小（核心 runtime ~10KB），对 AI 代码生成友好。pywebview 复用系统 WebView 而不打包 Chromium，使最终安装包控制在 30–60 MB（Electron 通常 100 MB+）。

**目标平台优先级：**
1. Windows（首要，全力保证可用）
2. macOS（尽力而为）
3. Linux（尽力而为）

---

## MVP 范围

MVP 的目标是：**一个可运行、可测试、能完成完整整理流程的最小版本。**

### 必须实现

- 选择文件夹（点击选择按钮）
- 扫描文件树，展示树状结构和文件数量
- 检测重复文件（同名 + SHA1 相同）
- 选择内置提示词（5 个预设）
- 生成并复制发送给 AI 的文本（文件清单 + 提示词）
- 整理要求输入框（自然语言描述整理目标）
- 调用 AI 生成整理方案（`generate_plan` API，MVP 必须实现）
- 展示整理后树状图（当前文件树 vs 整理后文件树，本地计算生成）
- 展示操作列表（新建/移动/重命名/删除说明）
- 支持手动编辑 AI 返回的 JSON
- 导入 JSON（作为 AI 不可用、调试或用户手动调整时的备用方式）
- 支持重新生成（修改整理要求后再次调用 AI）
- 预览整理操作（冲突、缺失路径警告）
- 执行 `create_dir` / `move` / `rename` / `delete_dir`
- 冲突处理（`auto_rename` / `skip` / `ask`）
- 执行结果弹窗（成功/跳过/错误统计）
- 当前会话撤销（内存 undo stack）
- 基础设置页：AI 服务商、模型、API Key、冲突策略、排除规则
- 深色/浅色主题切换

### 暂缓（Phase 5 增强）

- 历史页与持久化撤销（跨会话）
- Windows 原生拖放（拖文件自动填路径）
- 多语言 i18n（中英文切换）
- PyInstaller 打包
- GitHub Actions CI
- 代码签名
- 自动更新
- 自定义提示词高级搜索
- 多轮 AI 对话（永久非目标：FolderMind 使用单次请求模式，不做聊天窗口）

**AI 接入策略：**
- MVP 直接包含真实 AI 接入：用户输入单次整理要求，后端调用 `generate_plan`，AI 返回 JSON plan。
- 导入/粘贴 JSON 保留为备用入口，用于 AI 不可用、调试或用户手动微调方案。
- FolderMind 不做通用聊天窗口、不做多轮追问；用户不满意方案时，修改整理要求后重新生成。

---

## 非目标

以下功能**不在任何阶段实现**，明确拒绝：

- 不读取文件内容（只读取文件名、路径、大小、修改时间）
- 不上传文件内容到任何服务器
- 不做云同步
- 不内置数据库
- 不做自动更新
- 不删除普通文件，只删除空文件夹
- 不支持同时选择多个根文件夹
- 不支持扫描压缩包内部内容
- 不支持 OCR
- 不支持根据文件正文内容判断分类
- **不支持覆盖已有文件**（冲突时只允许自动重命名或跳过）
- 不递归删除非空目录（`delete_dir` 只删空目录）

---

## 核心功能说明

### 文件扫描（scanner.py）

- `fast_scan(path, progress_callback, exclude_rules)`：递归遍历，使用 `os.scandir`（比 `os.walk` 快 3–5 倍），目录级 prune 排除规则
- `find_duplicates(file_list)`：同名 + 大小差 < 1 KB 初筛，SHA1 二次确认；空文件不参与
- `generate_tree(path, file_list)`：生成树状目录字符串，用于界面展示
- `generate_for_ai(file_list)`：生成"相对路径  修改时间"格式的纯文本清单

**文件数量分档（`smart_output`）：**

| 文件数 | 行为 |
|---|---|
| ≤ 100 | 直接发送 |
| 101–500 | 弹出警告"可能超出部分模型上下文限制，建议选更小的子文件夹"，用户确认后可发送 |
| > 500 | 强制导出为 .md 文件，用户手动复制给 AI |

**大文件夹保护：** 总文件数 > 50,000 或总大小 > 50 GB 时弹出警告，建议选子文件夹；用户可继续，不强制阻止。

**硬编码排除（用户无法关闭）：**

- 版本控制：`.git` `.svn` `.hg`
- 编辑器/IDE：`.idea` `.vscode`
- 语言/环境：`node_modules` `__pycache__` `.venv` `venv` `env` `target` `dist` `build`
- 系统垃圾：`.DS_Store` `Thumbs.db` `desktop.ini` `.localized`

**用户可配置排除：** gitignore 风格 glob，pathspec 库解析，目录级命中时直接 prune 不递归。

---

### 操作执行（executor.py）

支持四种操作类型：

| 类型 | 说明 |
|---|---|
| `create_dir` | 新建文件夹。目标已存在且是目录视为成功；目标是文件则报错 |
| `move` | 移动文件到新路径。父目录必须已存在（不自动创建，要求 AI 先输出 `create_dir`）。按冲突策略处理目标冲突 |
| `rename` | 在指定目录内重命名文件。按冲突策略处理目标冲突 |
| `delete_dir` | 删除空文件夹。执行前静默清理系统垃圾文件，非空时报错跳过 |

**安全检查：** 所有路径经 `Path.resolve()` 后与根目录比较，拒绝操作根目录以外的路径（防路径穿越），拒绝绝对路径输入。

---

### 提示词管理（prompts.py）

5 个内置预设：

| 名称 | 用途 |
|---|---|
| 整理归类 | 按文件用途分类，建立清晰文件夹结构 |
| 学习计划 | 根据修改时间和文件名判断学习优先级 |
| 归档清理 | 找出超过 1 年未修改的旧文件，移到归档文件夹 |
| 项目整理 | 按 src/docs/assets/config 等项目规范整理 |
| 重命名规范 | 统一用「日期_描述」格式重命名混乱文件 |

每个提示词末尾附有强制规则：使用正斜杠路径、不编造文件名、不删除普通文件、操作顺序（先建目录再移动再删目录）、只输出 JSON 不输出其他文字。

删除非空文件夹的强制规则：AI 必须先列出所有文件的 `move` 操作，`delete_dir` 按从深到浅顺序排列。

---

### 历史记录（logger.py — Phase 5）

历史记录底层分为两类，UI 上合并展示为整理活动时间线。

**AiGenerationRecord（AI 生成记录）：** 记录调用过 AI 生成方案这件事。
- 包含：id、rootPath、createdAt、provider、model、promptKey/Name、userInstruction、summary、actionCount、status（generated/failed/executed/discarded）、executionId（若已执行）
- 未执行的方案：默认不保存完整 actions JSON
- AI 原始响应文本：默认不保存（避免历史文件过大）

**ExecutionRecord（执行记录）：** 记录真的改了文件这件事。
- 包含：id、rootPath、createdAt、source（ai_generated/manual_json）、sourceGenerationId（关联 AI 生成记录）
- successCount / skippedCount / errorCount
- **actions 必须保存**（解析后的执行方案）
- **results 必须保存**（每条 action 的执行结果）
- **undoStack 必须保存**（用于重启后撤销）
- undoStatus：available / undone / unavailable

**历史 UI 时间线（4 种情况）：**

| 情况 | 显示内容 | 可操作 |
|---|---|---|
| AI 生成并执行 | 路径 + 模型 + 要求 + 操作数 + 执行统计 | 查看详情 / 撤销 |
| AI 生成未执行 | 路径 + 模型 + 要求 + 操作数 + 未执行 | 查看方案 / 删除 |
| 手动导入 JSON 执行 | 路径 + 来源: 手动导入 + 执行统计 | 查看详情 / 撤销 |
| 仅扫描文件夹 | 不保存历史 | --- |

**保存策略：** 每次执行独立 JSON 文件（`~/.foldermind_logs/{timestamp}.json`），最多保留 100 条（设置可改）。

---

### 配置持久化（config.py）

配置文件：`~/.foldermind_config.json`（不含明文 API Key）

包含：
- 当前 AI 服务商（anthropic / openai / custom）
- 每个服务商最后选中的模型及自定义模型列表
- 自定义 Endpoint URL
- 自定义提示词列表
- 已删除的预设提示词键名
- 冲突处理策略
- 排除规则列表
- 界面语言（zh-CN / en）
- 主题（dark / light）
- 配置版本号（`config_version`，初版为 1）

**API Key 存储：** `keyring` 库写入操作系统密钥环（Windows Credential Manager / macOS Keychain / Linux Secret Service），按 provider 维度分别存储。可选"仅本次运行"内存模式（程序退出即失效）。配置文件本身永远不含明文 Key。

---

### AI 调用（api.py）

FolderMind 的 AI 接入采用**单次需求输入 + 本地可视化预览**的方式，不做通用聊天窗口。

**核心流程：** 用户输入整理要求 → 程序将文件清单、用户要求、预设提示词和严格 JSON 输出规则合并为 prompt → 调用 AI API → AI 返回 JSON plan → 本地校验 + 计算整理后树状图 → 用户确认后执行。

**职责划分：**
- AI 的职责：只生成 `Plan`（JSON 格式的操作列表）
- 本地程序的职责：JSON 解析、schema 校验、路径安全检查、冲突检测、整理后树状图生成、操作执行、撤销
- **AI 不直接执行任何文件操作**

**流式响应：** 默认走 SSE 流式接口，用户能看到 AI 逐步生成 JSON，避免长时间静默等待。

**超时与重试：** 单次超时 60 秒。遇 429 / 5xx / 网络中断时指数退避（1s / 2s / 4s）重试 3 次。尊重 `Retry-After` header。

**测试连接：** 发送 max_tokens=8 的最小请求，超时 15 秒，返回成功或具体错误原因。

支持的服务商：

| 服务商 | Endpoint | 认证 |
|---|---|---|
| Anthropic | `https://api.anthropic.com/v1/messages` | `x-api-key` |
| OpenAI | `https://api.openai.com/v1/chat/completions` | `Authorization: Bearer` |
| 自定义 | 用户填写 | `Authorization: Bearer` |

---

## UI 布局

### 整体框架

```
┌────────────┬──────────────────────────────────────────────────┐
│            │ 顶栏：文件夹路径框  [选择] [扫描]  [🌙][☀️]      │
│  侧边栏    ├──────────────────────────────────────────────────┤
│            │ 内容区（随页面切换）                              │
│  ⚡ 整理   │                                                  │
│  ⚙ 设置   │                                                  │
│            ├──────────────────────────────────────────────────┤
│            │ 底部栏：状态指示  [预览] [执行整理] [撤销]        │
└────────────┴──────────────────────────────────────────────────┘
```

### 整理页

**左栏（228px 固定）：** 文件树面板，文件夹蓝色、重复文件橙色，底部显示重复文件提示。

**右栏 — AI 整理要求面板：**
- **提示词芯片区：** 预设整理风格列表（单击选中，双击编辑，悬停删除），末尾「＋ 新建」
- **整理要求输入框：** 自然语言文本区，用户描述整理目标
- **操作按钮行：** 「生成整理方案」/ 「重新生成」/ 「导入 JSON」（备用入口）
- **AI 原始 JSON 区：** 可折叠 textarea，显示 AI 返回的原始 JSON，支持手动编辑后重新解析
- FolderMind 不做聊天窗口。不满意方案时，修改整理要求后重新生成，而非多轮对话

**底部状态栏：**
- 彩色状态圆点（绿色=就绪，橙色闪烁=进行中，红色=错误）+ 状态文字
- 预览、执行整理、撤销三个按钮，按流程逐步解锁

### 设置页

两栏布局：

**左栏：** AI 服务商选择（分段控件）、模型管理、自定义 Endpoint URL、API Key 输入（密码型，可选仅内存模式）、测试连接、冲突处理策略（单选）、排除规则（textarea）、语言切换（预留，MVP 暂不实现）

**右栏：** 提示词管理（搜索框过滤 + 新建，预设/自定义标签，支持编辑和删除）

### 弹窗

**操作预览弹窗（整理后树状图）：** 展示整理方案的完整可视化预览，内容分三个区域：
- 左侧：当前文件树
- 右侧：整理后文件树（由本地程序根据 `Plan.actions` 计算，不依赖 AI 再解释）
- 底部：操作列表（新建文件夹 / 移动文件 / 重命名文件 / 删除空文件夹）+ 冲突和缺失路径警告
底部有取消、「编辑 JSON」（返回修改）和确认执行三个按钮。AI 不直接执行任何文件操作，所有操作必须经过本地校验和用户确认。

**冲突询问弹窗（ask 策略）：** 具体冲突详情（源/目标/目标已有内容），提供"重命名 / 跳过"两个选项（不含覆盖），"应用到剩余所有冲突"复选框。

**执行结果弹窗：** 成功/跳过/错误三个统计卡片，点击可筛选日志列表，底部有撤销按钮（有可撤销操作时显示）。

---

## 安全机制

- 所有文件操作路径经 `Path.resolve()` 后与根目录比较，拒绝根目录外路径（防路径穿越）
- `delete_dir` 只删空文件夹，非空时报错；执行前静默清理系统垃圾文件白名单
- 执行前 `validate_actions` 预检所有路径和冲突，统一在预览弹窗提示用户确认
- API Key 存于操作系统密钥环；配置文件永远不含明文 Key
- AI 返回内容经 JSON 格式验证后才执行，格式错误直接报错不执行
- 硬编码排除规则用户无法关闭，避免误操作版本控制和依赖目录
- **MVP 不支持覆盖文件**，冲突策略只允许自动重命名和跳过，消除覆盖导致数据丢失的风险

---

## 已知限制

- 撤销仅对程序自己执行过的操作有效；用户在程序外手动删除/移动的文件无法恢复（操作系统限制）
- 文件数 > 500 时强制导出 .md 文件，需用户手动复制给 AI
- pywebview 需使用 Python 3.12（Python 3.14 因 pythonnet 不兼容无法安装）
- AI 仅基于文件名和修改时间判断，不读取内容；对内容相关的整理判断能力有限

---

## 打包与分发

- **构建顺序：** `pnpm build`（前端）→ PyInstaller 打包
- **工具：** PyInstaller 单文件模式（`--onefile`），配置文件 `build.spec`
- **产物：** Windows `.exe`，macOS `.app/.dmg`，Linux AppImage
- **关键细节（Windows）：** `--collect-all webview`，`--add-data "ui/dist:ui/dist"`
- **代码签名（生产发布必需）：** Windows SmartScreen 需代码签名证书，macOS 需 Apple Developer ID
- **更新机制：** v1 不做自动更新，用户手动下载

> 打包属于 Phase 5 增强阶段，MVP 阶段直接 `python main_gui.py` 运行。

---

## 开发环境配置

### Python 后端

```bash
# 必须使用 Python 3.12
py -3.12 -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install pywebview==5.x httpx==0.27.x pathspec==0.12.x keyring==25.x pytest==8.x
```

### 前端

```bash
# 需要 Node 20 LTS（最低 18）
npm install -g pnpm
cd frontend
pnpm install
```

### 开发模式启动

```bash
# 终端 1：Vite 开发服务器
cd frontend && pnpm dev        # 监听 http://localhost:5173

# 终端 2：Python 主程序
python main_gui.py --dev       # 连接 Vite dev server
```

VS Code 用户按 F5（`launch.json` 已配置同时启动两个进程）。

### 依赖版本锁定

后续在 `requirements.txt` 和 `frontend/package.json` 中固定具体版本号，减少环境差异导致生成代码不可运行的风险。
