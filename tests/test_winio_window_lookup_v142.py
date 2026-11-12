"""Window selection without focusing a window or sending input."""
import sys
from types import SimpleNamespace

import pytest

if sys.platform != "win32":
    pytest.skip("Win32 window adapter", allow_module_level=True)

import winio


def test_lookup_prefers_visible_game_client_to_helper_and_title_fallback(monkeypatch):
    io = winio.WinIO()
    windows = {
        1: ("Fortnite", "FortniteClient-Win64-Shipping.exe", False),
        2: ("Fortnite", "FortniteClient-Win64-Shipping_EAC_EOS.exe", True),
        3: ("Fortnite", "", True),
        4: ("Fortnite", "browser.exe", True),
        5: ("Fortnite (DX12)", "FortniteClient-Win64-Shipping.exe", True),
    }

    def enumerate_windows(callback, value):
        return all(callback(hwnd, value) for hwnd in windows)

    monkeypatch.setattr(winio, "user32", SimpleNamespace(
        EnumWindows=enumerate_windows,
        IsWindowVisible=lambda hwnd: windows[hwnd][2],
    ))
    monkeypatch.setattr(io, "_window_title", lambda hwnd: windows[hwnd][0])
    monkeypatch.setattr(io, "_process_name", lambda hwnd: windows[hwnd][1])

    assert io._find_game() == 5
    windows.pop(5)
    assert io._find_game() == 3
    windows.pop(3)
    assert not io.game_window_found()


def test_foreground_check_rejects_a_window_that_lost_focus(monkeypatch):
    io = winio.WinIO()
    foreground = iter((101, 102))
    monkeypatch.setattr(winio, "user32", SimpleNamespace(
        GetForegroundWindow=lambda: next(foreground),
    ))
    monkeypatch.setattr(io, "_process_name", lambda hwnd: "FortniteClient-Win64-Shipping.exe")
    assert not io.game_in_foreground()
