# FolderMind

[English](README.en.md) | 中文

![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-TBD-orange)

FolderMind 是一个 Windows 桌面文件整理工具：扫描文件夹，让 AI 生成整理方案，先预览，再安全执行。

## 截图

> 建议把中文主界面截图放到 `docs/images/zh/main.png`，然后取消下面这一行的注释。

<!-- ![FolderMind 主界面](docs/images/zh/main.png) -->

## 功能特性

- 扫描文件夹并展示文件结构，支持大目录扫描进度和取消。
- 支持拖入文件夹或 JSON 文件。
- 内置多种整理风格：整理归类、学习计划、归档清理、项目整理、重命名规范。
- 支持自定义提示词，并提供中英文模板。
- 可复制 AI 上下文；内容过大时自动导出为文件。
- 支持 AI 对话、流式返回、中断请求和复制对话内容。
- 支持导入 AI 返回的 JSON，并在执行前预览变化。
- 执行前显示缺失、冲突和错误信息。
- 支持历史记录，查看扫描、预览、执行和撤销结果。
- 支持浅色 / 深色主题和中英文界面。

## 系统要求

- Windows 10 / Windows 11
- Python 3.12 或更高版本
- Node.js 18 或更高版本
- npm
- WebView2 Runtime，一般 Windows 11 已自带

## 安装

克隆仓库：

```powershell
git clone https://github.com/your-name/FolderMind.git
cd FolderMind
```

创建虚拟环境：

```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装 Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

安装前端依赖：

```powershell
npm.cmd install --prefix frontend
```

开发模式运行前端：

```powershell
npm.cmd run dev --prefix frontend
```

另开一个终端运行桌面程序：

```powershell
.\.venv\Scripts\python.exe main_gui.py --dev
```

## 使用流程

1. 点击顶部“选择”，选择需要整理的文件夹。
2. 程序会自动扫描文件夹，并在左侧显示文件结构。
3. 在右侧选择整理风格，例如“整理归类”或“学习计划”。
4. 点击“发送给 AI”，等待 AI 返回 JSON 整理方案。
5. 检查 AI 返回的 JSON，也可以手动导入 `.json` 或 `.txt` 文件。
6. 点击“执行整理”。
7. 在预览窗口中查看整理前后变化、缺失文件和冲突信息。
8. 确认无误后执行整理。
9. 如果当次执行支持撤销，可以点击“撤销”恢复本次操作。
10. 在“历史”页面查看扫描、预览、执行和撤销记录。

## API 配置

FolderMind 支持三类 AI 服务商：

- Anthropic (Claude)
- OpenAI (GPT)
- Custom，适用于 OpenAI 兼容接口，例如第三方中转站或其他兼容平台

配置步骤：

1. 进入“设置”页面。
2. 选择服务商。
3. 填写模型名称。
4. 填写 API Endpoint。
5. 填写 API Key。
6. 点击“测试连接”，查看是否能正常访问。
7. 点击“保存设置”。

默认 Endpoint：

- Anthropic: `https://api.anthropic.com/v1/messages`
- OpenAI: `https://api.openai.com/v1/chat/completions`
- Custom: 需要自己填写；如果只填根地址，程序会尝试补全聊天接口路径

关于 API Key：

- 配置文件 `config/config.json` 不保存 API Key。
- 程序会优先使用系统凭据管理器保存 Key。
- 如果系统凭据管理器不可用，当前实现会退回到 `config/api_keys.json`。如果你要公开发布，请不要提交 `config/` 目录。

## 提示词

内置预设：

- 整理归类：按用途、主题和类型整理。
- 学习计划：按课程、知识领域、资料类型和优先级整理学习资料。
- 归档清理：把旧资料和低频文件移动到归档目录。
- 项目整理：按项目结构整理代码、文档、素材、配置和输出物。
- 重命名规范：整理混乱但含义明确的文件名。

自定义提示词：

- 可以在主页点击整理风格区域的 `+` 新建。
- 也可以在设置页的“提示词管理”中新建。
- 两个入口使用同一套模板。
- 新模板会自动包含文件列表占位符和严格 JSON 输出约束。
- 切换中英文后，提示词名称和内容会使用对应语言版本。

提示词要求 AI 只返回 FolderMind 支持的 JSON，并且 action type 只能是：

- `create_dir`
- `move`
- `rename`
- `delete_dir`

## 注意事项

- 撤销只在当次程序运行中有效；关闭程序后不能保证还能撤销上一次执行。
- 程序不会删除任何文件。`delete_dir` 只允许删除已经清空的文件夹。
- 执行整理前一定先看预览，尤其是缺失、冲突和错误详情。
- 文件数较多时，“复制内容”会自动变成“导出文件”。当前规则是：超过 500 个文件，或上下文文本超过 120000 字符时导出到 `foldermind_ai_context.md`。
- AI 对话默认最多发送 1000 个文件的信息，可以在设置里调整，范围是 50 到 5000。
- 历史记录保存在程序目录下的 `history/history.json`，里面可能包含本地路径和 AI 返回内容，不建议上传到 GitHub。
- 配置保存在程序目录下的 `config/config.json`，不建议上传到 GitHub。

## 打包

如果你想生成一个可直接双击运行的文件夹版本：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build_exe.py
```

打包结果：

```text
release/
  FolderMind/
    FolderMind.exe
    _internal/
    frontend/
      dist/
    config/
    history/
```

分发时请发送整个 `release/FolderMind` 文件夹，不要只发送 `FolderMind.exe`。

## 常见问题 FAQ

### 测试连接失败怎么排查？

先检查这几项：

- API Key 是否填写完整。
- 服务商是否选对。
- 模型名称是否真实存在。
- Endpoint 是否完整。
- Custom 服务商建议填写完整地址，例如 `https://api.example.com/v1/chat/completions`。
- 网络是否能访问对应服务。
- 如果返回 404，通常是 Endpoint 路径不对。
- 如果返回 401 或 403，通常是 Key 无效、余额不足或没有模型权限。
- 如果超时，可以在设置里调大超时时间，或更换服务商 / 网络环境。

### 支持哪些 AI 模型？

FolderMind 不限制具体模型，只要服务商接口兼容即可。

常见选择：

- Claude 系列，例如 `claude-opus-4-6`、`claude-sonnet-4-6`
- OpenAI 模型，例如 `gpt-4o`、`gpt-4.1`、`o3`
- OpenAI 兼容模型，例如 DeepSeek、通义、硅基流动或其他第三方平台提供的模型

### 不接入 API 能用吗？

可以使用扫描、复制内容、导出上下文、导入 JSON、预览和执行整理。  
只有“发送给 AI”需要配置 API。

### AI 返回的 JSON 执行不了怎么办？

先点击预览，看缺失、冲突和错误详情。常见原因包括：

- `from` 路径和文件列表不完全一致。
- AI 自创了不支持的 action type。
- JSON 外面混入了解释文字或 Markdown。
- 文件已经被移动、删除或改名。

### 会不会删除我的文件？

不会删除文件。  
FolderMind 的执行器只支持删除空文件夹，不支持删除文件。

### 为什么历史记录不要上传 GitHub？

历史记录里可能包含你的本地文件路径、文件名、AI 返回 JSON 和执行结果。  
这些属于个人运行数据，不适合公开。

## 开发测试

运行后端测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

构建前端：

```powershell
npm.cmd run build --prefix frontend
```
