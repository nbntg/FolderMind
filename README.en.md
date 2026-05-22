# FolderMind

English | [中文](README.md)

![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-TBD-orange)

FolderMind is a Windows desktop tool for scanning a folder, asking AI to generate an organization plan, previewing the plan, and safely executing file operations.

## Screenshot

> Put the English main interface screenshot at `docs/images/en/main.png`, then uncomment the line below.

<!-- ![FolderMind main interface](docs/images/en/main.png) -->

## Features

- Scan a folder and display its file structure, with progress and cancellation for large folders.
- Drag in folders or JSON files.
- Built-in organization styles: category organization, study plan, archive cleanup, project structure, and rename rules.
- Custom prompts with Chinese and English templates.
- Copy AI context; automatically export to a file when the content is too large.
- AI chat with streaming responses, request interruption, and conversation copying.
- Import AI-generated JSON and preview changes before execution.
- Show missing files, conflicts, and errors before execution.
- History page for scan, preview, execute, and undo results.
- Light / dark theme and Chinese / English UI.

## System Requirements

- Windows 10 / Windows 11
- Python 3.12 or later
- Node.js 18 or later
- npm
- WebView2 Runtime, usually bundled with Windows 11

## Installation

Clone the repository:

```powershell
git clone https://github.com/your-name/FolderMind.git
cd FolderMind
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Install frontend dependencies:

```powershell
npm.cmd install --prefix frontend
```

Run the frontend in development mode:

```powershell
npm.cmd run dev --prefix frontend
```

Open another terminal and run the desktop app:

```powershell
.\.venv\Scripts\python.exe main_gui.py --dev
```

## Usage

1. Click “Choose” and select the folder you want to organize.
2. FolderMind scans the folder and shows the file structure on the left.
3. Select an organization style on the right.
4. Click “Send to AI” and wait for a JSON organization plan.
5. Review the returned JSON, or import a `.json` / `.txt` file manually.
6. Click “Execute”.
7. Review the before / after preview, missing files, and conflicts.
8. Confirm to execute the plan.
9. If the current run supports undo, click “Undo” to revert the latest execution.
10. Open the History page to review scan, preview, execute, and undo records.

## API Configuration

FolderMind supports three provider types:

- Anthropic (Claude)
- OpenAI (GPT)
- Custom, for OpenAI-compatible endpoints such as third-party relay services

Configuration steps:

1. Open Settings.
2. Select a provider.
3. Enter the model name.
4. Enter the API Endpoint.
5. Enter the API Key.
6. Click “Test connection”.
7. Click “Save settings”.

Default endpoints:

- Anthropic: `https://api.anthropic.com/v1/messages`
- OpenAI: `https://api.openai.com/v1/chat/completions`
- Custom: user-defined. If only a base URL is entered, FolderMind will try to complete the chat endpoint path.

About API keys:

- `config/config.json` does not store API keys.
- FolderMind prefers the system credential manager.
- If the credential manager is unavailable, the current implementation falls back to `config/api_keys.json`. Do not commit the `config/` directory when publishing.

## Prompts

Built-in presets:

- Organize by Category
- Study Plan
- Archive Cleanup
- Project Structure
- Rename Rules

Custom prompts:

- Create one from the `+` button on the main page.
- Or create one in Settings > Prompt manager.
- Both entries use the same template.
- New templates include the file list placeholder and strict JSON output rules.
- When switching language, prompt names and content use the matching language version.

FolderMind only accepts these action types:

- `create_dir`
- `move`
- `rename`
- `delete_dir`

## Notes

- Undo is only reliable within the current app session.
- FolderMind never deletes files. `delete_dir` can only remove empty folders.
- Always preview before execution, especially missing files, conflicts, and errors.
- When content is large, “Copy content” becomes “Export file”. Current rule: more than 500 files, or context text longer than 120000 characters, exports to `foldermind_ai_context.md`.
- AI chat sends up to 1000 file entries by default. This can be changed in Settings from 50 to 5000.
- History is stored in `history/history.json` and may contain local paths and AI output. Do not commit it.
- Settings are stored in `config/config.json`. Do not commit it.

## Packaging

To build a portable folder with `FolderMind.exe`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build_exe.py
```

Output:

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

Distribute the whole `release/FolderMind` folder, not only `FolderMind.exe`.

## FAQ

### How do I troubleshoot connection test failures?

Check the API key, provider, model name, endpoint, network access, and account permissions. A 404 usually means the endpoint path is wrong. A 401 or 403 usually means the key is invalid, the account has no balance, or the selected model is unavailable.

### Which AI models are supported?

FolderMind does not hardcode model restrictions. It can use Anthropic models, OpenAI models, and OpenAI-compatible models such as DeepSeek or other third-party provider models.

### Can I use FolderMind without an API?

Yes. Scanning, copying context, exporting context, importing JSON, previewing, and executing do not require an API. Only “Send to AI” requires API configuration.

### What if the AI JSON cannot be executed?

Preview first and check missing files, conflicts, and errors. Common causes include mismatched `from` paths, unsupported action types, Markdown around the JSON, or files that were moved outside FolderMind.

### Will FolderMind delete my files?

No. The executor does not support file deletion. It can only delete empty folders.

## Development Tests

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Build the frontend:

```powershell
npm.cmd run build --prefix frontend
```
