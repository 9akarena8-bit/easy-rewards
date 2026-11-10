"""UI-independent application logic for Easy Rewards.
Every public method listed in Backend.API takes and returns plain JSON-able values, so the same class
serves the pywebview window (webapp.py), the test shim and anything else.  No Windows-only imports here:
the screen/keyboard layer (`io`) is injected.
"""
from __future__ import annotations

import base64
import collections
import threading
import time
from pathlib import Path

import cv2
import numpy as np

import updater
import treasure
from core import ROLES, Config, Engine, best_match, imread_unicode, load_templates
from i18n import LANGS, STRINGS
from tracker import Tracker

NUM_LIMITS = {
    "threshold": (float, 0.30, 0.99),
    "scan_interval": (float, 0.1, 5.0),
    "click_delay": (float, 0.0, 30.0),
    "afk_interval": (float, 1.0, 120.0),
    "afk_hold": (float, 0.1, 10.0),
}
BOOLS = ("require_foreground", "auto_focus", "afk_enabled", "auto_update", "guide_dismissed", "treasure_auto_boost")
STRS = {"language": ("ru", "en", "uk", "de", "fr", "es", "pt", "pl", "tr", "it", "ja", "ko", "zh", "ar"),
        "theme": ("light", "dark"),  "ui_language": LANGS}
SHOT_MAX_W = 1600

def safe_name(name: str) -> str:
    return "".join(ch for ch in str(name) if ch.isalnum() or ch in "-")[:40] or "button"

class Hooks:
    before_capture = None
    after_capture = None
    open_mini = None
    close_mini = None
    save_dialog = None
    open_dialog = None

class Backend:
    API = (
        "state", "strings", "start", "stop", "pause", "reset_stats", "set_config",
        "templates", "delete_template", "capture_screenshot", "save_template", "test_templates",
        "counter_add", "counter_set", "counter_edit", "counter_new", "counter_delete", "tokens_add",
        "prize_add", "prize_toggle", "prize_delete", "tracker_set", "tracker_export", "tracker_import",
        "tracker_reset", "update_check", "update_install", "open_mini", "close_mini",
    )

    def __init__(self, base, io, hooks: Hooks | None = None):
        self.base = Path(base)
        self.io = io
        self.hooks = hooks or Hooks()
        self.cfg_path = self.base / "config.json"
        self.templates_root = self.base / "templates"
        self.cfg = Config.load(self.cfg_path)
        self.tracker = Tracker(self.base / "tracker.json")
        self._log: collections.deque = collections.deque(maxlen=80)
        self._log_n = 0
        self.engine = Engine(self.cfg, io, self.templates_root, log=self.log)
        self._shot: np.ndarray | None = None
        self._manifest: dict | None = None
        self._upd = {"status": "idle", "version": "", "notes": "", "error": ""}
        self._lock = threading.Lock()
        self.restart_requested = False
        self.version = updater.local_version(self.base)

    def log(self, key: str, /, **kw) -> None:
        self._log_n += 1
        self._log.append({"n": self._log_n, "t": time.strftime("%H:%M:%S"), "key": key, "kw": kw})

    def strings(self, lang: str | None = None) -> dict:
        lang = lang if lang in LANGS else self.cfg.ui_language
        return {**STRINGS["en"], **STRINGS.get(lang, {})}

    def _save_cfg(self) -> None:
        self.cfg.save(self.cfg_path)

    def shutdown(self) -> None:
        self.engine.stop()
        self._save_cfg()

    def _history(self) -> list[dict]:
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
        if trs["active"] and self.cfg.treasure_auto_boost:
            if prev is None or (prev is not None and not prev):
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
            "cfg": {k: getattr(self.cfg, k) for k in Config.__dataclass_fields__},
            "engine": {"state": e.state, "running": e.running, "paused": e.paused, "score": round(e.score, 3),
                       "games": e.games, "cycles": e.cycles, "runtime": int(e.runtime),
                       "history": self._history()},
            "tpl_counts": counts,
            "guide": {"c1": counts["start"] > 0, "c2": counts["result"] > 0,
                      "c3": (e.games + e.cycles) > 0, "dismissed": bool(self.cfg.guide_dismissed)},
            "log": [{"n": r["n"], "t": r["t"], "key": r["key"], "kw": r["kw"]} for r in list(self._log)[-40:]],
            "tracker": t.snapshot(),
            "luck": t.luck(),
            "week": t.week_info(),
            "update": dict(self._upd),
            "treasure": trs,
        }

    def start(self) -> None:
        self.engine.start()

    def stop(self) -> None:
        self.engine.stop()

    def pause(self) -> None:
        self.engine.toggle_pause()

    def reset_stats(self) -> None:
        self.engine.reset_stats()

    def set_config(self, patch: dict) -> dict:
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
        self._save_cfg()
        return {"ok": not rejected, "rejected": rejected}

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

    def update_check(self, url: str | None = None) -> dict:
        url = (url if url is not None else self.cfg.update_url).strip()
        if not url:
            self._upd = {"status": "need_url", "version": "", "notes": "", "error": ""}
            return self._upd
        if url != self.cfg.update_url:
            res = self.set_config({"update_url": url})
            if not res["ok"]:
                self._upd = {"status": "error", "version": "", "notes": "", "error": "https"}
                return self._upd
        self._upd = {"status": "checking", "version": "", "notes": "", "error": ""}
        try:
            version, manifest = updater.check(self.base, url)
        except Exception as exc:
            self._upd = {"status": "error", "version": "", "notes": "", "error": str(exc)}
            return self._upd
        self._manifest = manifest
        if manifest is None:
            self._upd = {"status": "latest", "version": self.version, "notes": "", "error": ""}
        else:
            self._upd = {"status": "available", "version": version, "notes": str(manifest.get("notes", "")),
                         "error": ""}
        return self._upd

    def update_install(self) -> dict:
        if not self._manifest:
            return {"status": "error", "version": "", "notes": "", "error": "nothing to install"}
        try:
            version = updater.install(self.base, self._manifest)
        except Exception as exc:
            self._upd = {"status": "error", "version": "", "notes": "", "error": str(exc)}
            return self._upd
        self._manifest = None
        self._upd = {"status": "installed", "version": str(version), "notes": "", "error": ""}
        self.restart_requested = True
        return self._upd

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
    
