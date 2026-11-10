"""pywebview shell: native window around ui/index.html, plus the always-on-top mini window."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import webview  # pip install pywebview  (needs Microsoft WebView2, present on Windows 10/11)

import winio
from backend import Backend, Hooks

BASE = Path(__file__).resolve().parent
UI = BASE / "ui" / "index.html"


def main() -> int:
    hooks = Hooks()
    backend = Backend(BASE, winio.WinIO(), hooks)

    class JsApi:
        pass
    for name in Backend.API:
        setattr(JsApi, name, (lambda n: lambda self, *a: getattr(backend, n)(*a))(name))

    main_win = webview.create_window("Easy Rewards", UI.as_uri(), js_api=JsApi(), width=1180, height=760,
                                     min_size=(900, 600))
    mini = {"w": None}

    def open_mini():
        if mini["w"] is not None:
            return
        mini["w"] = webview.create_window("Easy Rewards", UI.as_uri() + "?mini=1", js_api=JsApi(), width=300,
                                          height=250, on_top=True, resizable=False)
        mini["w"].events.closed += lambda: mini.update(w=None)

    def close_mini():
        if mini["w"] is not None:
            mini["w"].destroy()

    def save_dialog(name):
        r = main_win.create_file_dialog(webview.SAVE_DIALOG, save_filename=name)
        return (r if isinstance(r, str) else (r[0] if r else None))

    def open_dialog():
        r = main_win.create_file_dialog(webview.OPEN_DIALOG)
        return r[0] if r else None

    hooks.before_capture, hooks.after_capture = main_win.minimize, main_win.restore
    hooks.open_mini, hooks.close_mini, hooks.save_dialog, hooks.open_dialog = open_mini, close_mini, save_dialog, open_dialog

    winio.HotkeyPoller({"F7": backend.engine.start, "F8": backend.engine.stop,
                        "F9": backend.hotkey_count, "F10": backend.engine.toggle_pause}).start()

    def auto_update():
        time.sleep(4)
        if backend.cfg.auto_update and backend.cfg.update_url:
            if backend.update_check()["status"] == "available":
                backend.update_install()
    threading.Thread(target=auto_update, daemon=True).start()

    webview.start()
    backend.shutdown()
    if backend.restart_requested:
        if os.environ.get("EASY_REWARDS_LAUNCHER"):
            return 42
        subprocess.Popen([sys.executable] + sys.argv)
    return 0
