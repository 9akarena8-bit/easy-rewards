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


def test_combo_attempts_remaining_key_releases_after_error(monkeypatch):
    events = []

    def key(scan, up):
        events.append((scan, up))
        if up and scan == winio.SCANCODES["d"]:
            raise OSError("release rejected")

    monkeypatch.setattr(winio, "_key", key)
    with pytest.raises(OSError, match="release rejected"):
        winio.WinIO().hold_combo("wd", 0, lambda: False)
    assert events == [
        (winio.SCANCODES["w"], False), (winio.SCANCODES["d"], False),
        (winio.SCANCODES["d"], True), (winio.SCANCODES["w"], True),
    ]


def test_aim_releases_right_button_even_if_left_release_fails(monkeypatch):
    events = []

    def mouse(flag):
        events.append(flag)
        if flag == winio.MOUSEEVENTF_LEFTUP:
            raise OSError("release rejected")

    monkeypatch.setattr(winio, "_mouse", mouse)
    with pytest.raises(OSError, match="release rejected"):
        winio.WinIO().aim_and_fire(0, lambda: False)
    assert events[-2:] == [winio.MOUSEEVENTF_LEFTUP, winio.MOUSEEVENTF_RIGHTUP]
