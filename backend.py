"""UI-independent application logic for Easy Rewards.

Every public method listed in Backend.API takes and returns plain JSON-able values, so the same class
serves the pywebview window (webapp.py), the test shim and anything else.  No Windows-only imports here:
the screen/keyboard layer (`io`) is injected.
"""
from __future__ import annotations

import base64
import sys
import collections
import threading
import time
from pathlib import Path

import cv2
import numpy as np

import updater
import treasure
import release_updater
import subscription_preview
import payment_hub
import support_report
import discord_notifications
import webbrowser
from core import ROLES, Config, Engine, best_match, imread_unicode, load_templates
from i18n import LANGS, STRINGS
from tracker import Tracker
from reward_stats import RewardStats

NUM_LIMITS = {          # key: (type, lo, hi)
    "threshold": (float, 0.30, 0.99),
    "scan_interval": (float, 0.1, 5.0),
    "click_delay": (float, 0.0, 30.0),
    "afk_interval": (float, 1.0, 120.0),
    "afk_hold": (float, 0.1, 10.0),
    "afk_pause_min": (float, 0.2, 10.0),
    "afk_pause_max": (float, 0.2, 10.0),
    "afk_camera_pixels_360": (float, 100.0, 12000.0),
}
# Reserve F6 input test, F9 counter and F10 pause. Distinct Start/Stop keys.
AFK_HOTKEY_CHOICES = tuple(f"F{i}" for i in range(1, 13) if i not in (6, 9, 10))
BOOLS = ("require_foreground", "auto_focus", "afk_enabled", "afk_launch_game", "auto_update", "guide_dismissed", "treasure_auto_boost", "afk_extra_enabled", "afk_sequence_enabled", "afk_jump_enabled", "afk_sprint_enabled",
         "afk_slide_enabled", "afk_camera_enabled", "afk_slot_enabled", "afk_pickaxe_enabled",
         "afk_grenade_enabled", "afk_weapon_enabled", "afk_replay_auto_detect")
STRS = {"language": ("ru", "en", "uk", "de", "fr", "es", "pt", "pl", "tr", "it", "ja", "ko", "zh", "ar"),
        "theme": ("light", "dark"), "ui_language": LANGS}
SHOT_MAX_W = 1600


def safe_name(name: str) -> str:
    return "".join(ch for ch in str(name) if ch.isalnum() or ch in "-_")[:40] or "button"


class Hooks:
    """Window-system callbacks the shell may provide. All optional."""
    before_capture = None   # () -> None   hide the app window
    after_capture = None    # () -> None   show it again
    open_mini = None
    close_mini = None
    save_dialog = None      # (suggested_name) -> path | None
    open_dialog = None      # () -> path | None


class Backend:
    API = (
        "state", "strings", "start", "stop", "pause", "focus_game_now", "reset_stats", "set_config",
        "templates", "delete_template", "capture_screenshot", "save_template", "test_templates",
        "counter_add", "counter_set", "counter_edit", "counter_new", "counter_delete", "tokens_add",
        "prize_add", "prize_toggle", "prize_delete", "tracker_set", "tracker_export", "tracker_import",
        "tracker_reset", "update_check", "update_prepare", "update_install", "open_mini", "close_mini",
        "input_probe_delayed", "create_support_report", "open_support",
        "discord_configure", "discord_test", "discord_clear",
        "payment_interest_create",
    )

    def __init__(self, base, io, hooks: Hooks | None = None):
        self.base = Path(base)
        self.io = io
        self.hooks = hooks or Hooks()
        self.cfg_path = self.base / "config.json"
        self.templates_root = self.base / "templates"
        self.cfg = Config.load(self.cfg_path)
        # Never let a malformed/old config disable emergency Stop or bind
        # reserved F12 as Start. Settings can also be edited outside the UI.
        start_key = str(self.cfg.afk_start_hotkey).upper()
        stop_key = str(self.cfg.afk_stop_hotkey).upper()
        if start_key not in AFK_HOTKEY_CHOICES or start_key == "F12":
            start_key = "F7"
        if stop_key not in AFK_HOTKEY_CHOICES or stop_key == start_key:
            stop_key = "F8" if start_key != "F8" else "F12"
        self.cfg.afk_start_hotkey = start_key
        self.cfg.afk_stop_hotkey = stop_key
        self.tracker = Tracker(self.base / "tracker.json")
        self._log: collections.deque = collections.deque(maxlen=80)
        self._log_n = 0
        self.discord = discord_notifications.DiscordNotifications(self.base / "discord_notifications.json")
        # Records calls that REACHED Python, including global F8/F10 hotkeys.
        self._control_sequence = 0
        self._control_action = "none"
        self._control_time = ""
        self.reward_stats = RewardStats(self.base / "rewards.json")
        self.payment_drafts = payment_hub.LocalInterestDrafts(self.base / "payment_interest_drafts.json")
        self.engine = Engine(self.cfg, io, self.templates_root, log=self.log,
                             on_reward=self.reward_stats.increment)
        self._shot: np.ndarray | None = None
        self._manifest: dict | None = None
        self._release_manifest: dict | None = None
        self.release_mode = bool(getattr(sys, "frozen", False))
        self._upd = {"status": "idle", "version": "", "notes": "", "error": ""}
        self._verified_installer: Path | None = None
        self._release_news: list[dict] = []
        self._update_lock = threading.RLock()
        self._lock = threading.Lock()
        self.restart_requested = False
        self.version = updater.local_version(self.base)

    # ------------------------------------------------------------ plumbing
    def log(self, key: str, /, **kw) -> None:
        self._log_n += 1
        self._log.append({"n": self._log_n, "t": time.strftime("%H:%M:%S"), "key": key, "kw": kw})
        # Strict allowlist: Discord never receives log arguments, tokens, user data or paths.
        elapsed = int(self.engine.runtime) if key == "log.stopped" and hasattr(self, "engine") else None
        self.discord.notify(key, runtime_seconds=elapsed)

    def discord_configure(self, webhook_url: str = "", enabled: bool = False) -> dict:
        return self.discord.configure(webhook_url, enabled)

    def discord_test(self) -> dict:
        accepted = self.discord.notify("discord_test", test=True)
        return {"ok": accepted, "error": "" if accepted else "Enable Discord notifications first"}

    def discord_clear(self) -> dict:
        return self.discord.clear()

    def _control_received(self, action: str) -> None:
        self._control_sequence += 1
        self._control_action = action
        self._control_time = time.strftime("%H:%M:%S")

    def payment_interest_create(self, plan: str, method: str, game: str = "",
                                skin_selection: dict | None = None) -> dict:
        """Save a local, non-payable request. NEVER accept payment or grant access."""
        return self.payment_drafts.create(plan, method, game, skin_selection)

    def create_support_report(self) -> dict:
        """User-triggered local diagnostic file. Never auto-upload or leak secrets."""
        try:
            status = self.state()
            text = support_report.report_text(
                self.version, self.engine, status["diagnostics"],
                status["controls"], status["log"])
            destination = support_report.save_report(self.base, text)
            return {"ok": True, "path": str(destination), "text": text}
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:180]}

    def open_support(self, channel: str) -> dict:
        """Open only an explicitly verified official support URL."""
        url = support_report.verified_contact(str(channel))
        if not url:
            return {"ok": False, "error": "support_link_not_configured"}
        try:
            opened = bool(webbrowser.open(url, new=2))
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:180]}
        return {"ok": opened, "error": "" if opened else "browser_not_available"}

    def strings(self, lang: str | None = None) -> dict:
        lang = lang if lang in LANGS else self.cfg.ui_language
        return {**STRINGS["en"], **STRINGS.get(lang, {})}

    def _save_cfg(self) -> None:
        self.cfg.save(self.cfg_path)

    def shutdown(self) -> None:
        self.engine.stop()
        self._save_cfg()

    # ------------------------------------------------------------ state
    def _history(self) -> list[dict]:
        """Six 10-minute buckets, oldest first."""
        now = time.time()
        out = [{"games": 0, "cycles": 0} for _ in range(6)]
        for key, times in (("games", self.engine.game_times), ("cycles", self.engine.cycle_times)):
            for t in list(times):
                age = now - t
                if 0 <= age < 3600:
                    out[5 - int(age // 600)][key] += 1
        return out

    def _template_counts(self) -> dict:
        counts = {r: 0 for r in ROLES}
        folder = self.templates_root / self.cfg.language
        if folder.is_dir():
            for p in folder.glob("*.png"):
                role = p.stem.split("_", 1)[0].lower()
                if role in counts:
                    counts[role] += 1
        return counts

    def _treasure(self) -> dict:
        trs = treasure.treasure_state(self.base / "treasure.json")
        prev = getattr(self, "_tr_active", None)
        if trs["active"] and self.cfg.treasure_auto_boost and prev is not True:
            self.tracker.set_options({"boost": trs["pirate_mult"]})
        if prev is not None and trs["active"] != prev:
            if trs["active"]:
                self.log("log.treasure_start", m=trs["pirate_mult"], odds=trs["pirate_odds"])
            else:
                self.log("log.treasure_end")
                if self.cfg.treasure_auto_boost:
                    self.tracker.set_options({"boost": 1.0})
        self._tr_active = trs["active"]
        return trs

    def state(self) -> dict:
        e = self.engine
        counts = self._template_counts()
        t = self.tracker
        trs = self._treasure()
        return {
            "version": self.version,
            "release_mode": self.release_mode,
            "support_contacts": support_report.contacts(),
            "discord_notifications": self.discord.status(),
            "controls": {"last": self._control_action,
                         "time": self._control_time,
                         "sequence": self._control_sequence},
            "cfg": {k: getattr(self.cfg, k) for k in Config.__dataclass_fields__},
            "engine": {"state": ("stopping" if e.stopping else "paused" if e.paused and e.running else e.state), "running": e.running, "paused": e.paused, "score": round(e.score, 3),
                       "games": e.games, "cycles": e.cycles, "rewards": e.rewards, "runtime": int(e.runtime),
                       "history": self._history(),
                       "input_count": e.input_count, "last_input": e.last_input,
                       "input_error": e.last_input_error,
                       "wait_reason": e.wait_reason,
                       "probe_status": e.probe_status, "probe_detail": e.probe_detail,
                       "probe_at": e.probe_at, "probe_target": e.probe_target,
                       "replay_count": e.replay_count, "replay_status": e.replay_status,
                       "replay_source": e.replay_source, "replay_attempts": e.replay_attempts,
                       "focus_result": e.focus_result},
            "reward": {"session": e.rewards, "total": self.reward_stats.total},
            "diagnostics": {
                "foreground_title": (self.io.foreground_title() if hasattr(self.io, "foreground_title") else ""),
                "game_active": bool(self.io.game_in_foreground()),
                "game_found": bool(self.io.game_window_found()) if hasattr(self.io, "game_window_found") else False,
                "foreground_process": (self.io.foreground_process() if hasattr(self.io, "foreground_process") else ""),
                "game_title": str(getattr(self.io, "window_title", "Fortnite")),
                "template_count": len(e.templates),
            },
            "tpl_counts": counts,
            "guide": {"c1": counts["start"] > 0, "c2": counts["result"] > 0,
                      "c3": (e.games + e.cycles) > 0, "dismissed": bool(self.cfg.guide_dismissed)},
            "log": [{"n": r["n"], "t": r["t"], "key": r["key"], "kw": r["kw"]} for r in list(self._log)[-40:]],
            "tracker": t.snapshot(),
            "luck": t.luck(),
            "week": t.week_info(),
            "update": dict(self._upd),
            "release_news": list(self._release_news),
            "subscription": subscription_preview.snapshot(),
            "payment_hub": {**payment_hub.catalog(),
                            "drafts": self.payment_drafts.recent()},
            "treasure": trs,
        }

    # ------------------------------------------------------------ engine controls
    def start(self) -> dict:
        """Start the engine; optionally request Fortnite launch via Epic protocol.

        Dispatching a URI is not proof that the game has started. The engine
        waits for a verified foreground Fortnite window before sending input.
        """
        self._control_received("start")
        if self.engine.running:
            self.engine.start()  # existing resume / queued-restart semantics
            return {"ok": True, "reason": "already_running"}
        if self.cfg.afk_launch_game and not getattr(self.io, "game_window_found", lambda: False)():
            launcher = getattr(self.io, "launch_game", None)
            if callable(launcher):
                try:
                    if not launcher():
                        return {"ok": False, "reason": "epic_launcher_unavailable"}
                except (OSError, ValueError) as exc:
                    return {"ok": False, "reason": "epic_launch_error", "detail": str(exc)[:180]}
                self.engine.start()
                return {"ok": True, "reason": "launch_requested"}
        # Test IO adapters and disabled auto-launch continue to work without Epic.
        self.engine.start()
        if self.cfg.auto_focus and getattr(self.io, "game_window_found", lambda: False)():
            try:
                self.io.focus_game()
            except (OSError, RuntimeError):
                pass
        return {"ok": True, "reason": "started"}

    def input_probe_delayed(self, target: str = "fortnite") -> dict:
        """Schedule a test while the user switches to the target window."""
        self._control_received("probe_" + str(target))
        if target not in ("fortnite", "notepad"):
            return {"ok": False, "reason": "invalid_target"}
        if self.engine.running:
            return {"ok": False, "reason": "stop_first"}
        if self.engine.probe_status == "scheduled":
            return {"ok": False, "reason": "already_scheduled"}
        self.engine.probe_status = "scheduled"
        self.engine.probe_target = target
        self.engine.probe_detail = f"Focus {target} within 3 seconds"
        def run():
            time.sleep(3)
            self.engine.input_probe(target)
        threading.Thread(target=run, name="afk-input-test", daemon=True).start()
        return {"ok": True}

    def stop(self) -> None:
        self._control_received("stop")
        self.engine.stop()

    def pause(self) -> None:
        self._control_received("pause")
        self.engine.toggle_pause()

    def focus_game_now(self) -> dict:
        """Switch only to a verified Fortnite window, if Windows permits it."""
        self._control_received("focus")
        try:
            if not hasattr(self.io, "game_window_found") or not self.io.game_window_found():
                self.engine.focus_result = "not_found"
                return {"ok": False, "reason": "not_found"}
            focused = bool(self.io.game_in_foreground() or self.io.focus_game())
            self.engine.focus_result = "focused" if focused else "denied"
            return {"ok": focused, "reason": "focused" if focused else "denied"}
        except Exception as exc:
            self.engine.focus_result = "error: " + repr(exc)
            return {"ok": False, "reason": "error", "detail": repr(exc)}

    def reset_stats(self) -> None:
        self.engine.reset_stats()

    # ------------------------------------------------------------ config
    def set_config(self, patch: dict) -> dict:
        """Apply validated settings. Returns {"ok": bool, "rejected": [keys]}."""
        rejected = []
        for k, v in (patch or {}).items():
            try:
                if k in NUM_LIMITS:
                    typ, lo, hi = NUM_LIMITS[k]
                    setattr(self.cfg, k, max(lo, min(hi, typ(v))))
                elif k in BOOLS:
                    setattr(self.cfg, k, bool(v))
                elif k in STRS:
                    if v not in STRS[k]:
                        raise ValueError(k)
                    setattr(self.cfg, k, v)
                elif k in ("afk_start_hotkey", "afk_stop_hotkey"):
                    key = str(v).strip().upper()
                    other = ("afk_stop_hotkey" if k == "afk_start_hotkey"
                             else "afk_start_hotkey")
                    if (key not in AFK_HOTKEY_CHOICES or
                            (k == "afk_start_hotkey" and key == "F12") or
                            key == getattr(self.cfg, other)):
                        raise ValueError(k)
                    setattr(self.cfg, k, key)
                elif k == "afk_keys":
                    keys = "".join(dict.fromkeys(c for c in str(v).lower() if c in "wasd"))
                    if not keys:
                        raise ValueError(k)
                    self.cfg.afk_keys = keys
                elif k == "update_url":
                    v = str(v).strip()
                    if v and not v.lower().startswith("https://"):
                        raise ValueError(k)
                    self.cfg.update_url = v
                else:
                    rejected.append(k)
            except (TypeError, ValueError):
                rejected.append(k)
        # Keep the pause range valid even if only one endpoint was edited.
        if self.cfg.afk_pause_min > self.cfg.afk_pause_max:
            if "afk_pause_min" in (patch or {}):
                self.cfg.afk_pause_max = self.cfg.afk_pause_min
            else:
                self.cfg.afk_pause_min = self.cfg.afk_pause_max
        self._save_cfg()
        return {"ok": not rejected, "rejected": rejected}

    # ------------------------------------------------------------ templates
    def templates(self) -> list[dict]:
        out = []
        folder = self.templates_root / self.cfg.language
        for p in sorted(folder.glob("*.png")) if folder.is_dir() else []:
            role = p.stem.split("_", 1)[0].lower()
            img = imread_unicode(p)
            if role not in ROLES or img is None or not img.size:
                continue
            h, w = img.shape[:2]
            thumb = img
            if w > 220:
                thumb = cv2.resize(img, (220, max(1, round(h * 220 / w))), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".png", thumb)
            out.append({"name": p.stem, "role": role, "w": w, "h": h,
                        "thumb": "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode() if ok else ""})
        return out

    def delete_template(self, name: str) -> bool:
        p = self.templates_root / self.cfg.language / f"{safe_name(name)}.png"
        if p.is_file():
            p.unlink()
            return True
        return False

    def capture_screenshot(self, delay: float = 5.0) -> dict:
        """Hide the window, wait, grab the screen. The full frame stays here; the UI gets a preview."""
        delay = max(0.0, min(15.0, float(delay)))
        if self.hooks.before_capture:
            self.hooks.before_capture()
        try:
            time.sleep(delay)
            frame = self.io.grab()
        finally:
            if self.hooks.after_capture:
                self.hooks.after_capture()
        self._shot = frame
        h, w = frame.shape[:2]
        prev = frame
        if w > SHOT_MAX_W:
            prev = cv2.resize(frame, (SHOT_MAX_W, round(h * SHOT_MAX_W / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", prev, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return {"ok": bool(ok), "w": w, "h": h,
                "image": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()}

    def save_template(self, role: str, name: str, fx: float, fy: float, fw: float, fh: float) -> dict:
        if role not in ROLES:
            return {"ok": False, "error": "role"}
        if self._shot is None:
            return {"ok": False, "error": "no_shot"}
        H, W = self._shot.shape[:2]
        x, y = int(round(max(0.0, min(1.0, fx)) * W)), int(round(max(0.0, min(1.0, fy)) * H))
        w, h = int(round(max(0.0, min(1.0, fw)) * W)), int(round(max(0.0, min(1.0, fh)) * H))
        x2, y2 = min(W, x + w), min(H, y + h)
        if x2 - x < 8 or y2 - y < 8:
            return {"ok": False, "error": "small"}
        crop = self._shot[y:y2, x:x2]
        path = self.templates_root / self.cfg.language / f"{role}_{safe_name(name)}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        ok, buf = cv2.imencode(".png", crop)
        if not ok:
            return {"ok": False, "error": "encode"}
        buf.tofile(str(path))
        self.log("log.capture_saved", name=path.name, w=x2 - x, h=y2 - y)
        return {"ok": True, "name": path.stem}

    def test_templates(self) -> dict:
        tpls = load_templates(self.templates_root, self.cfg.language)
        if not tpls:
            return {"ok": False, "scores": []}
        gray = cv2.cvtColor(self.io.grab(), cv2.COLOR_BGR2GRAY)
        scores = [{"name": t.name, "role": t.role,
                   "score": round(max(0.0, best_match(gray, t.gray, self.cfg.scales)[0]), 3)} for t in tpls]
        return {"ok": True, "threshold": self.cfg.threshold, "scores": scores}

    # ------------------------------------------------------------ tracker (thin, error-safe wrappers)
    def _t(self, fn, *a, **kw):
        try:
            return {"ok": True, "value": fn(*a, **kw)}
        except (KeyError, ValueError, TypeError) as exc:
            return {"ok": False, "error": str(exc)}

    def counter_add(self, cid, delta):
        return self._t(self.tracker.counter_add, cid, int(delta))

    def counter_set(self, cid, value):
        return self._t(self.tracker.counter_set, cid, value)

    def counter_edit(self, cid, name=None, goals=None):
        return self._t(self.tracker.counter_edit, cid, name, goals)

    def counter_new(self, name, goals=None):
        return self._t(self.tracker.counter_new, name, goals)

    def counter_delete(self, cid):
        return self._t(self.tracker.counter_delete, cid)

    def tokens_add(self, delta):
        return self._t(self.tracker.tokens_add, int(delta))

    def prize_add(self, name):
        return self._t(self.tracker.prize_add, name)

    def prize_toggle(self, pid):
        return self._t(self.tracker.prize_toggle, pid)

    def prize_delete(self, pid):
        return self._t(self.tracker.prize_delete, pid)

    def tracker_set(self, patch):
        return self._t(self.tracker.set_options, patch or {})

    def hotkey_count(self) -> None:
        """F9: +1 on the first counter."""
        snap = self.tracker.snapshot()
        if snap["counters"]:
            self.tracker.counter_add(snap["counters"][0]["id"], 1)

    def tracker_export(self, path=None):
        path = path or (self.hooks.save_dialog("easy-rewards-tracker.json") if self.hooks.save_dialog
                        else str(self.base / "easy-rewards-tracker.json"))
        if not path:
            return {"ok": False, "error": "cancelled"}
        try:
            self.tracker.export_to(path)
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": str(path)}

    def tracker_import(self, path=None):
        path = path or (self.hooks.open_dialog() if self.hooks.open_dialog else None)
        if not path:
            return {"ok": False, "error": "cancelled"}
        try:
            self.tracker.import_from(path)
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def tracker_reset(self):
        self.tracker.reset()
        return {"ok": True}

    def refresh_release_news(self) -> list[dict]:
        """Fetch public, non-executable release headlines in the background only."""
        if not self.release_mode:
            return list(self._release_news)
        try:
            items = release_updater.release_news()
        except Exception as exc:
            self.log("log.error", err="release news: " + str(exc))
            return list(self._release_news)
        self._release_news = items
        return list(items)

    # ------------------------------------------------------------ updates
    def update_check(self, url: str | None = None) -> dict:
        """Check releases without triggering an installation.

        The locking prevents the 5-minute background poll from racing a click
        to exit-and-update or a cached-installer download.
        """
        if self.release_mode:
            with self._update_lock:
                if self._upd["status"] in ("ready", "downloading", "installer_started"):
                    return dict(self._upd)
                self._upd = {"status": "checking", "version": "", "notes": "", "error": ""}
                self._release_manifest = None
                try:
                    self._release_manifest = release_updater.latest_release(self.version)
                    if self._release_manifest is None:
                        self._upd = {"status": "latest", "version": self.version, "notes": "", "error": ""}
                    else:
                        self._upd = {"status": "available", "version": self._release_manifest["version"],
                                     "notes": self._release_manifest.get("notes", ""), "error": ""}
                except Exception as exc:
                    self._upd = {"status": "error", "version": "", "notes": "", "error": str(exc)}
                return dict(self._upd)
        url = (url if url is not None else self.cfg.update_url).strip()
        if not url:
            self._upd = {"status": "need_url", "version": "", "notes": "", "error": ""}
            return dict(self._upd)
        if url != self.cfg.update_url:
            res = self.set_config({"update_url": url})
            if not res["ok"]:
                self._upd = {"status": "error", "version": "", "notes": "", "error": "https"}
                return dict(self._upd)
        self._upd = {"status": "checking", "version": "", "notes": "", "error": ""}
        try:
            version, manifest = updater.check(self.base, url)
        except Exception as exc:
            self._upd = {"status": "error", "version": "", "notes": "", "error": str(exc)}
            return dict(self._upd)
        self._manifest = manifest
        if manifest is None:
            self._upd = {"status": "latest", "version": self.version, "notes": "", "error": ""}
        else:
            self._upd = {"status": "available", "version": version, "notes": str(manifest.get("notes", "")),
                         "error": ""}
        return dict(self._upd)

    def update_prepare(self) -> dict:
        """Download and SHA-256 verify an installer, but NEVER execute it.

        Called only from the background release watcher after explicit opt-in
        via auto_update. Safe to run while a game is active.
        """
        if not self.release_mode:
            return dict(self._upd)
        with self._update_lock:
            meta = self._release_manifest
            if meta is None or self._upd.get("status") == "installer_started":
                return dict(self._upd)
            if self._verified_installer and release_updater.verify_installer(meta, self._verified_installer):
                self._upd = {"status": "ready", "version": meta["version"],
                             "notes": meta.get("notes", ""), "error": ""}
                return dict(self._upd)
            self._upd = {"status": "downloading", "version": meta["version"],
                         "notes": meta.get("notes", ""), "error": ""}
            try:
                self._verified_installer = release_updater.download_installer(meta)
                self._upd["status"] = "ready"
            except Exception as exc:
                self._verified_installer = None
                self._upd = {"status": "error", "version": meta["version"],
                             "notes": meta.get("notes", ""), "error": str(exc)}
            return dict(self._upd)

    def update_install(self) -> dict:
        """User-initiated install: stop engine, verify installer, open wizard."""
        if self.release_mode:
            with self._update_lock:
                meta = self._release_manifest
                if meta is None:
                    return {"status": "error", "version": "", "notes": "",
                            "error": "No verified GitHub release has been selected"}
                if self.engine.running:
                    self.engine.stop()
                    # Screen capture/OpenCV may finish asynchronously after F8.
                    # Give it a bounded time to release input before replacing files.
                    worker = self.engine._thread
                    if worker is not None and worker.is_alive() and worker is not threading.current_thread():
                        worker.join(timeout=5.0)
                    if self.engine.running:
                        return {"status": "error", "version": meta["version"], "notes": "",
                                "error": "Stop in progress: Anti-AFK is still stopping. Try again in a moment."}
                self._upd = {"status": "downloading", "version": meta["version"], "notes": "", "error": ""}
                try:
                    installer = self._verified_installer
                    if not installer or not release_updater.verify_installer(meta, installer):
                        installer = release_updater.download_installer(meta)
                    # Only release_updater.launch_installer runs the installer.
                    release_updater.launch_installer(installer)
                    self._verified_installer = None
                    self._release_manifest = None
                    self._upd = {"status": "installer_started", "version": meta["version"],
                                 "notes": "", "error": ""}
                except Exception as exc:
                    self._upd = {"status": "error", "version": meta["version"],
                                 "notes": "", "error": str(exc)}
                return dict(self._upd)
        if not self._manifest:
            return {"status": "error", "version": "", "notes": "", "error": "nothing to install"}
        try:
            version = updater.install(self.base, self._manifest)
        except Exception as exc:
            self._upd = {"status": "error", "version": "", "notes": "", "error": str(exc)}
            return dict(self._upd)
        self._manifest = None
        self._upd = {"status": "installed", "version": str(version), "notes": "", "error": ""}
        self.restart_requested = True
        return dict(self._upd)

    # ------------------------------------------------------------ mini window
    def open_mini(self) -> bool:
        if self.hooks.open_mini:
            self.hooks.open_mini()
            return True
        return False

    def close_mini(self) -> bool:
        if self.hooks.close_mini:
            self.hooks.close_mini()
            return True
        return False
