"""Windows implementation of the IO interface used by the engine.

Screen capture : Pillow ImageGrab
Mouse/keyboard : SendInput (scan codes, so games accept them)
Hotkeys        : GetAsyncKeyState polling (works while the game has focus)
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from typing import Callable

import cv2
import numpy as np
from PIL import ImageGrab

if sys.platform != "win32":
    raise ImportError("winio only works on Windows")

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # pixel-accurate coordinates
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0002, 0x0008
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
SCANCODES = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20}
VK = {"F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.WPARAM)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", wintypes.WPARAM)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send(inp: INPUT) -> None:
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _key(scan: int, up: bool) -> None:
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    _send(INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(0, scan, flags, 0, 0))))


def _mouse(flags: int) -> None:
    _send(INPUT(INPUT_MOUSE, _INPUTUNION(mi=MOUSEINPUT(0, 0, 0, flags, 0, 0))))


class WinIO:
    window_title = "Fortnite"

    def grab(self) -> np.ndarray:
        img = ImageGrab.grab()  # primary monitor
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def click(self, x: int, y: int) -> None:
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.06)
        _mouse(MOUSEEVENTF_LEFTDOWN)
        time.sleep(0.07)
        _mouse(MOUSEEVENTF_LEFTUP)

    def hold_key(self, key: str, seconds: float, should_abort: Callable[[], bool]) -> None:
        scan = SCANCODES.get(key.lower())
        if scan is None:
            return
        _key(scan, up=False)
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end and not should_abort():
                time.sleep(0.05)
        finally:
            _key(scan, up=True)

    # ---- game window helpers
    def _find_game(self):
        return user32.FindWindowW(None, self.window_title)

    def game_in_foreground(self) -> bool:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value.strip().lower() == self.window_title.lower()

    def focus_game(self) -> None:
        hwnd = self._find_game()
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)


class HotkeyPoller(threading.Thread):
    """Calls callbacks on key-down edges of F7 / F8 / F10."""

    def __init__(self, bindings: dict[str, Callable[[], None]]):
        super().__init__(daemon=True, name="hotkeys")
        self.bindings = {VK[k]: cb for k, cb in bindings.items()}

    def run(self) -> None:
        prev = {vk: False for vk in self.bindings}
        while True:
            for vk, cb in self.bindings.items():
                down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                if down and not prev[vk]:
                    try:
                        cb()
                    except Exception:
                        pass
                prev[vk] = down
            time.sleep(0.03)
