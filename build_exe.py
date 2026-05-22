from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
RELEASE_DIR = ROOT / "release"
APP_DIR = RELEASE_DIR / "FolderMind"


def run(command: list[str], cwd: Path = ROOT) -> None:
    print(">", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def npm_command() -> str:
    return "npm.cmd" if sys.platform.startswith("win") else "npm"


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "PyInstaller is not installed. Run:\n"
            r".\.venv\Scripts\python.exe -m pip install -r requirements-build.txt"
        ) from exc


def copy_frontend_dist() -> None:
    source = FRONTEND / "dist"
    target = APP_DIR / "frontend" / "dist"
    if not source.exists():
        raise SystemExit("frontend/dist was not created. Check npm build output.")
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)


def prepare_runtime_folders() -> None:
    (APP_DIR / "config").mkdir(parents=True, exist_ok=True)
    (APP_DIR / "history").mkdir(parents=True, exist_ok=True)


def clean_previous_output() -> None:
    if APP_DIR.exists():
        shutil.rmtree(APP_DIR)


def main() -> None:
    ensure_pyinstaller()
    clean_previous_output()
    run([npm_command(), "install", "--prefix", str(FRONTEND)])
    run([npm_command(), "run", "build", "--prefix", str(FRONTEND)])
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--windowed",
            "--name",
            "FolderMind",
            "--distpath",
            str(RELEASE_DIR),
            "--workpath",
            str(ROOT / "build" / "pyinstaller"),
            "--specpath",
            str(ROOT / "build" / "pyinstaller"),
            "--collect-all",
            "webview",
            "--collect-submodules",
            "keyring.backends",
            "--hidden-import",
            "clr",
            str(ROOT / "main_gui.py"),
        ]
    )
    copy_frontend_dist()
    prepare_runtime_folders()
    print()
    print(f"Done: {APP_DIR / 'FolderMind.exe'}")
    print("You can move the whole release/FolderMind folder together.")


if __name__ == "__main__":
    main()
