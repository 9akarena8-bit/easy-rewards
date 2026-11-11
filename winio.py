"""Windows screen/input adapter. No anti-cheat bypass; standard Win32 SendInput.

The input layer never installs a keyboard hook and releases held keys on exceptions.
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
kernel32 = ctypes.windll.kernel32
# Explicit pointer-sized signatures prevent truncated HWND/HANDLE values on Win64.
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SendInput.argtypes = (wintypes.UINT, ctypes.c_void_p, ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (OSError, AttributeError):
    try:
        user32.SetProcessDPIAware()
    except (OSError, AttributeError):
        pass

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0002, 0x0008
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MOVE = 0x0001
SCANCODES = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20, " ": 0x39,
             "space": 0x39, "shift": 0x2A, "ctrl": 0x1D, "y": 0x15,
             "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07}
VK = {"F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79}


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
    if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        code = kernel32.GetLastError()
        raise OSError(f"SendInput returned 0 (Win32 error={code}; permissions or protected app).")


def _key(scan: int, up: bool) -> None:
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    _send(INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(0, scan, flags, 0, 0))))


def _mouse(flags: int) -> None:
    _send(INPUT(INPUT_MOUSE, _INPUTUNION(mi=MOUSEINPUT(0, 0, 0, flags, 0, 0))))


class WinIO:
    window_title = "Fortnite"

    def grab(self) -> np.ndarray:
        image = ImageGrab.grab()  # foreground primary display in borderless windowed mode
        return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)

    def click(self, x: int | None = None, y: int | None = None) -> None:
        if (x is None) != (y is None):
            raise ValueError("Specify both click coordinates or neither")
        if x is not None:
            if not user32.SetCursorPos(int(x), int(y)):
                raise OSError("Cannot move the cursor")
        time.sleep(0.04)
        _mouse(MOUSEEVENTF_LEFTDOWN)
        try:
            time.sleep(0.05)
        finally:
            _mouse(MOUSEEVENTF_LEFTUP)

    def right_click(self, x: int | None = None, y: int | None = None) -> None:
        if (x is None) != (y is None):
            raise ValueError("Specify both click coordinates or neither")
        if x is not None:
            if not user32.SetCursorPos(int(x), int(y)):
                raise OSError("Cannot move the cursor")
        _mouse(MOUSEEVENTF_RIGHTDOWN)
        try:
            time.sleep(0.05)
        finally:
            _mouse(MOUSEEVENTF_RIGHTUP)

    def move_mouse(self, dx: int, dy: int) -> None:
        pt = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            raise OSError("Cannot read the cursor position")
        if not user32.SetCursorPos(pt.x + int(dx), pt.y + int(dy)):
            raise OSError("Cannot move the cursor")

    def press_key(self, key: str) -> None:
        scan = SCANCODES.get(str(key).lower())
        if scan is None:
            raise ValueError("Unsupported key: " + repr(key))
        _key(scan, up=False)
        try:
            time.sleep(0.065)
        finally:
            _key(scan, up=True)

    def hold_key(self, key: str, seconds: float, should_abort: Callable[[], bool]) -> None:
        scan = SCANCODES.get(str(key).lower())
        if scan is None:
            raise ValueError("Unsupported key: " + repr(key))
        if should_abort():
            return
        _key(scan, up=False)
        try:
            end = time.monotonic() + max(0.0, float(seconds))
            while time.monotonic() < end and not should_abort():
                time.sleep(min(0.05, max(0.0, end - time.monotonic())))
        finally:
            _key(scan, up=True)

    def hold_keys(self, keys, seconds: float, should_abort: Callable[[], bool]) -> None:
        """Send a timed combo, press keys in order and always release in reverse."""
        names = list(dict.fromkeys(str(k).lower() for k in keys))
        scans = []
        for name in names:
            if name not in SCANCODES:
                raise ValueError("Unsupported combo key: " + repr(name))
            scans.append(SCANCODES[name])
        held = []
        if should_abort():
            return
        try:
            for scan in scans:
                if should_abort():
                    return
                _key(scan, up=False)
                held.append(scan)
                # Ensure W / Shift / Ctrl have time to register as a sequence.
                if len(scans) > 1:
                    for _ in range(3):
                        if should_abort():
                            return
                        time.sleep(.018)
            end = time.monotonic() + max(0.0, float(seconds))
            while time.monotonic() < end and not should_abort():
                time.sleep(min(.03, end - time.monotonic()))
        finally:
            for scan in reversed(held):
                try:
                    _key(scan, up=True)
                except OSError:
                    pass

    def move_mouse_relative(self, dx: int, dy: int, seconds: float,
                            should_abort: Callable[[], bool]) -> None:
        """Relative mouse motion for camera controls, not cursor repositioning."""
        steps = max(1, min(120, int(max(.05, seconds) / .018)))
        interval = max(.008, float(seconds) / steps)
        sent_x = sent_y = 0
        for index in range(1, steps + 1):
            if should_abort():
                return
            x = round(int(dx) * index / steps)
            y = round(int(dy) * index / steps)
            diff_x, diff_y = x - sent_x, y - sent_y
            if diff_x or diff_y:
                _send(INPUT(INPUT_MOUSE, _INPUTUNION(mi=MOUSEINPUT(diff_x, diff_y, 0, MOUSEEVENTF_MOVE, 0, 0))))
                sent_x, sent_y = x, y
            end = time.monotonic() + interval
            while not should_abort() and time.monotonic() < end:
                time.sleep(min(.02, end - time.monotonic()))

    def hold_mouse(self, button: str, seconds: float,
                   should_abort: Callable[[], bool]) -> None:
        buttons = {"left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
                   "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)}
        if button not in buttons:
            raise ValueError("Unsupported mouse button: " + str(button))
        if should_abort():
            return
        down, up = buttons[button]
        _mouse(down)
        try:
            end = time.monotonic() + max(0.0, float(seconds))
            while not should_abort() and time.monotonic() < end:
                time.sleep(min(.03, end - time.monotonic()))
        finally:
            _mouse(up)

    def aim_and_fire(self, seconds: float, should_abort: Callable[[], bool]) -> None:
        """Hold RMB and LMB together; bounded duration, not ammo-aware."""
        if should_abort():
            return
        _mouse(MOUSEEVENTF_RIGHTDOWN)
        left_down = False
        try:
            time.sleep(.06)
            if should_abort():
                return
            _mouse(MOUSEEVENTF_LEFTDOWN)
            left_down = True
            end = time.monotonic() + max(0.0, float(seconds))
            while not should_abort() and time.monotonic() < end:
                time.sleep(min(.03, end - time.monotonic()))
        finally:
            if left_down:
                _mouse(MOUSEEVENTF_LEFTUP)
            _mouse(MOUSEEVENTF_RIGHTUP)

    def foreground_title(self) -> str:
        """Title of the active window; used only for diagnostics."""
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, len(buf))
        return buf.value.strip()

    def hold_combo(self, keys: str, seconds: float, should_abort: Callable[[], bool]) -> None:
        """Hold multiple movement keys safely; always release in reverse order."""
        scans = [SCANCODES[c] for c in dict.fromkeys(str(keys).lower()) if c in "wasd"]
        if not scans or should_abort():
            return
        held = []
        try:
            for scan in scans:
                if should_abort():
                    break
                _key(scan, up=False)
                held.append(scan)
            end = time.monotonic() + max(0., float(seconds))
            while time.monotonic() < end and not should_abort():
                time.sleep(min(.05, max(0., end - time.monotonic())))
        finally:
            for scan in reversed(held):
                _key(scan, up=True)

    def _process_name(self, hwnd) -> str:
        """Read the executable name of a visible window, without injecting or hooking."""
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(2048)
            size = wintypes.DWORD(len(buffer))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return buffer.value.rsplit("\\", 1)[-1]
            return ""
        finally:
            kernel32.CloseHandle(handle)

    def _looks_like_game(self, hwnd, title: str) -> bool:
        # Prefer process identity to a browser tab or unrelated window whose
        # title happens to contain "Fortnite". If Windows denies reading the
        # process name, the exact window title is a conservative fallback.
        process = self._process_name(hwnd).casefold()
        if process:
            return process.startswith("fortniteclient-") or process == "fortniteclient.exe"
        return title.strip().casefold() == self.window_title.casefold()

    def _find_game(self):
        found = user32.FindWindowW(None, self.window_title)
        if found and self._looks_like_game(found, self.window_title):
            return found
        # Game window titles may contain a prefix/suffix. Search only visible
        # top-level windows; never search process memory or inject into a game.
        windows = []
        def callback(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, buf, len(buf))
                if self._looks_like_game(hwnd, buf.value):
                    windows.append(hwnd)
                    return False
            return True
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(callback)
        user32.EnumWindows(enum_proc, 0)
        return windows[0] if windows else 0

    def game_window_found(self) -> bool:
        return bool(self._find_game())

    def foreground_process(self) -> str:
        return self._process_name(user32.GetForegroundWindow())

    def game_in_foreground(self) -> bool:
        hwnd = user32.GetForegroundWindow()
        return bool(hwnd and self._looks_like_game(hwnd, self.foreground_title()))

    def focus_game(self) -> None:
        hwnd = self._find_game()
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)


class HotkeyPoller(threading.Thread):
    """Global shortcuts using GetAsyncKeyState edge detection; no key recording."""

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
                        # A hotkey thread must not kill the GUI or leave keys held.
                        import traceback
                        traceback.print_exc()
                prev[vk] = down
            time.sleep(0.03)
