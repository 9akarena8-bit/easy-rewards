"""Native pywebview shell for Easy Rewards.

Windows 10/11: WebView2 is preferred. The frontend shows a descriptive error
instead of a blank window if the JS/Python bridge never becomes ready.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from paths import resources, data

import webview

import winio
from backend import Backend, Hooks

BASE = resources()
DATA = data()
UI = BASE / "ui" / "index.html"


def main() -> int:
    hooks = Hooks()
    backend = Backend(DATA, winio.WinIO(), hooks)
    backend.version = (BASE / "VERSION").read_text(encoding="utf-8").strip()
    main_win = None
    mini = {"w": None}
    maximized = {"value": False}

    class JsApi:
        """Typed Python API for the frontend; backend methods are attached below."""

        def window_minimize(self):
            if main_win is not None:
                main_win.minimize()

        def window_maximize(self):
            if main_win is None:
                return
            if maximized["value"]:
                main_win.restore()
            else:
                main_win.maximize()
            maximized["value"] = not maximized["value"]

        def window_close(self):
            if main_win is not None:
                main_win.destroy()

    for name in Backend.API:
        setattr(JsApi, name, (lambda n: lambda self, *a: getattr(backend, n)(*a))(name))

    # Win10 has no default rounded window chrome. Frameless mode lets the HTML
    # draw a compact title bar and softly rounded *inner* corners. Keep the
    # background opaque: pywebview doesn't support transparent Windows views.
    main_win = webview.create_window(
        "Easy Rewards", UI.as_uri(),
        js_api=JsApi(), width=1180, height=760,
        min_size=(900, 600), frameless=True, easy_drag=False,
        shadow=True, background_color="#08090b",
    )

    def open_mini():
        if mini["w"] is not None:
            return
        mini["w"] = webview.create_window(
            "Easy Rewards — Mini", UI.as_uri() + "?mini=1", js_api=JsApi(),
            width=300, height=250, on_top=True, resizable=False,
            background_color="#0c0d10",
        )
        mini["w"].events.closed += lambda: mini.update(w=None)

    def close_mini():
        if mini["w"] is not None:
            mini["w"].destroy()

    def save_dialog(name):
        r = main_win.create_file_dialog(webview.SAVE_DIALOG, save_filename=name)
        return r if isinstance(r, str) else (r[0] if r else None)

    def open_dialog():
        r = main_win.create_file_dialog(webview.OPEN_DIALOG)
        return r[0] if r else None

    hooks.before_capture = main_win.minimize
    hooks.after_capture = main_win.restore
    hooks.open_mini = open_mini
    hooks.close_mini = close_mini
    hooks.save_dialog = save_dialog
    hooks.open_dialog = open_dialog

    winio.HotkeyPoller({
        "F7": backend.engine.start,
        "F8": backend.engine.stop,
        "F9": backend.hotkey_count,
        "F10": backend.engine.toggle_pause,
    }).start()

    update_shutdown = threading.Event()

    def auto_update():
        if update_shutdown.wait(4):
            return
        while not update_shutdown.is_set():
            if backend.cfg.auto_update and (backend.release_mode or backend.cfg.update_url):
                if backend.state()["update"]["status"] not in ("ready", "downloading", "installer_started"):
                    result = backend.update_check()
                    if result["status"] == "available" and backend.release_mode:
                        backend.update_prepare()  # only download; never silently install
            if update_shutdown.wait(300):  # every 5 minutes, not only at startup
                break

    threading.Thread(target=auto_update, name="update-watcher", daemon=True).start()
    try:
        webview.start()
    finally:
        update_shutdown.set()
        backend.shutdown()

    if backend.restart_requested:
        if os.environ.get("EASY_REWARDS_LAUNCHER"):
            return 42
        subprocess.Popen([sys.executable] + sys.argv)
    return 0
