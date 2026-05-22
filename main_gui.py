from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

from core.config import load_history
from core.web_api import Api


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def frontend_index() -> Path:
    visible_index = app_dir() / "frontend" / "dist" / "index.html"
    if visible_index.exists():
        return visible_index
    bundled_root = Path(getattr(sys, "_MEIPASS", app_dir()))
    return bundled_root / "frontend" / "dist" / "index.html"


def inject_initial_history(window) -> None:
    payload = json.dumps(load_history(), ensure_ascii=False)
    window.evaluate_js(
        "window.__foldermindInitialHistory = "
        + payload
        + "; window.dispatchEvent(new CustomEvent('foldermind-history-loaded', { detail: window.__foldermindInitialHistory }));"
    )


def attach_drop_handler(window) -> None:
    def on_drop(event) -> None:
        files = event.get("dataTransfer", {}).get("files", [])
        if not files:
            return
        path = files[0].get("pywebviewFullPath") or files[0].get("path") or files[0].get("name")
        if path:
            window.evaluate_js(f"window.__foldermindDrop && window.__foldermindDrop({path!r})")

    body = window.dom.get_element("body")
    if body:
        body.on("drop", DOMEventHandler(on_drop, prevent_default=True, stop_propagation=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()

    url = "http://localhost:5173" if args.dev else str(frontend_index().resolve())
    window = webview.create_window("FolderMind", url, js_api=Api(), width=1180, height=780, min_size=(960, 620))
    window.events.loaded += inject_initial_history
    window.events.loaded += attach_drop_handler
    webview.start(debug=args.dev)


if __name__ == "__main__":
    main()
