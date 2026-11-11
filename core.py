"""Core logic: config, template matching and the automation engine.

Nothing in here is OS specific. All screen / keyboard / mouse access goes
through an `IO` object (see winio.py), which makes the engine testable.
"""
from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from i18n import tr

# Template file names are "<role>_<anything>.png".
#   start_*  : button that begins the next match (counts a game)
#   result_* : any button on result / reward screens (continue, claim all, back to lobby)
#   wait_*   : a loading / "connecting" screen - nothing is clicked and anti-AFK stays quiet
ROLES = ("start", "result", "wait", "reward")


# ----------------------------------------------------------------- config
@dataclass
class Config:
    language: str = "ru"            # game language -> templates/<language>/
    theme: str = "dark"            # "light" | "dark"
    ui_language: str = "ru"         # interface language: ru | en | uk
    update_url: str = ""            # https address of version.json (see updater.py)
    auto_update: bool = True        # check + install on start when update_url is set
    treasure_auto_boost: bool = True   # sync the tracker boost with live Treasure Hours
    guide_dismissed: bool = False   # hide the first-run checklist on the Home page
    threshold: float = 0.80         # recognition threshold (0..1)
    scan_interval: float = 0.5      # seconds between screen scans
    click_delay: float = 2.0        # min seconds between two clicks
    scales: list = field(default_factory=lambda: [1.0, 0.9, 1.1])
    require_foreground: bool = True  # only act while the game window is active
    auto_focus: bool = True          # try to bring the game window to front
    afk_enabled: bool = True
    afk_extra_enabled: bool = False  # opt in to jumps/clicks/item swaps
    afk_interval: float = 6.0       # seconds between anti-AFK presses
    afk_hold: float = 3.0           # max seconds a key is held
    afk_keys: str = "wasd"

    @classmethod
    def load(cls, path: Path) -> "Config":
        cfg = cls()
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            names = {f.name for f in fields(cls)}
            for k, v in data.items():
                if k in names:
                    setattr(cfg, k, v)
        except (OSError, ValueError):
            pass
        return cfg

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


# ------------------------------------------------------------- templates
@dataclass
class Template:
    name: str
    role: str
    gray: np.ndarray


def imread_unicode(path: Path) -> Optional[np.ndarray]:
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    except OSError:
        return None


def load_templates(root: Path, language: str) -> list[Template]:
    out: list[Template] = []
    folder = Path(root) / language
    for p in sorted(folder.glob("*.png")):
        role = p.stem.split("_", 1)[0].lower()
        if role not in ROLES:
            continue
        img = imread_unicode(p)
        if img is not None and img.size:
            out.append(Template(p.stem, role, img))
    return out


def best_match(frame_gray: np.ndarray, tpl: np.ndarray, scales) -> tuple[float, tuple[int, int]]:
    """Return (score, (cx, cy)) of the best multi-scale match."""
    best = (-1.0, (0, 0))
    fh, fw = frame_gray.shape[:2]
    for s in scales:
        t = tpl
        if abs(s - 1.0) > 1e-3:
            interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
            t = cv2.resize(tpl, None, fx=s, fy=s, interpolation=interp)
        th, tw = t.shape[:2]
        if th < 8 or tw < 8 or th >= fh or tw >= fw:
            continue
        res = cv2.matchTemplate(frame_gray, t, cv2.TM_CCOEFF_NORMED)
        res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
        _, mx, _, loc = cv2.minMaxLoc(res)
        if mx > best[0]:
            best = (float(mx), (loc[0] + tw // 2, loc[1] + th // 2))
    return best


# ---------------------------------------------------------------- engine
def _default_log(key: str, **kw) -> None:
    print(tr("en", key, **kw))


class Engine:
    """`log` is called as log(key, **kwargs); keys are translated by the UI (see i18n.py)."""

    def __init__(self, cfg: Config, io, templates_root: Path,
                 log: Callable[..., None] = _default_log,
                 on_reward: Callable[[], None] | None = None):
        self.cfg = cfg
        self.io = io
        self.templates_root = Path(templates_root)
        self.log = log
        self.on_reward = on_reward
        self.rewards = 0
        self._reward_visible = False
        self._reward_absent_since: float | None = None
        self._last_reward = -1e8

        self.templates: list[Template] = []
        self.state = "stopped"
        self.score = 0.0
        self.games = 0
        self.cycles = 0
        self.game_times: list[float] = []   # wall-clock times, used for the "last hour" bars
        self.cycle_times: list[float] = []
        self._run_seconds = 0.0
        self._tick_mark = 0.0

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._last_click = 0.0
        self._in_match = False
        self._result_seen = False
        self._next_afk = 0.0
        self.last_input = ""
        self.last_input_at = 0.0
        self.input_count = 0
        self.last_input_error = ""

    # ---- public controls (thread safe)
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def runtime(self) -> float:
        extra = 0.0
        if self.running and not self.paused:
            extra = time.monotonic() - self._tick_mark
        return self._run_seconds + extra

    def reload_templates(self) -> int:
        self.templates = load_templates(self.templates_root, self.cfg.language)
        return len(self.templates)

    def start(self) -> None:
        if self.running:
            if self.paused:
                self.toggle_pause()
            return
        n = self.reload_templates()
        # Anti-AFK mode must be runnable on a fresh install, even before
        # any screen templates have been captured.
        if n == 0 and not self.cfg.afk_enabled:
            self.log("log.no_templates", lang=self.cfg.language)
            return
        if n == 0:
            self.log("log.afk_only")
        self.log("log.started", n=n, lang=self.cfg.language)
        self._stop.clear()
        self._paused.clear()
        self._tick_mark = time.monotonic()
        self._next_afk = time.monotonic() + min(1.0, self._afk_wait())
        self.state = "starting"
        self.last_input_error = ""
        self._reward_visible = False
        self._reward_absent_since = None
        self._thread = threading.Thread(target=self._loop, name="engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self.running:
            return
        self._stop.set()
        self._thread.join(timeout=3)
        if self._thread.is_alive():
            self.log("log.error", err="Engine did not stop within 3 seconds")
            return
        self._thread = None
        self.state = "stopped"
        self.log("log.stopped")

    def toggle_pause(self) -> None:
        if not self.running:
            return
        if self.paused:
            self._tick_mark = time.monotonic()
            self._paused.clear()
            self.log("log.resumed")
        else:
            self._run_seconds += time.monotonic() - self._tick_mark
            self._paused.set()
            self.state = "paused"
            self.log("log.paused")

    def reset_stats(self) -> None:
        self.games = 0
        self.cycles = 0
        self.rewards = 0
        self.game_times.clear()
        self.cycle_times.clear()
        self._run_seconds = 0.0
        self._tick_mark = time.monotonic()

    # ---- internals
    def _afk_actions(self, should_abort: Callable[[], bool]) -> None:
        """Basic W/A/S/D holds. Extra actions are explicitly opt-in."""
        cfg = self.cfg
        if not cfg.afk_enabled or should_abort():
            return
        keys = "".join(dict.fromkeys(c for c in cfg.afk_keys.lower() if c in "wasd"))
        if not keys:
            return
        actions: list[tuple[str, Callable[[], None]]] = []
        direction = random.choice(keys)
        hold_cap = max(0.1, min(float(cfg.afk_hold), 10.0))
        hold = random.uniform(min(0.25, hold_cap), hold_cap)
        actions.append((direction.upper(), lambda d=direction, h=hold: self.io.hold_key(d, h, should_abort)))
        if getattr(cfg, "afk_extra_enabled", False):
            # Optional original movement variation: forward + sidestep.
            # This is not copied from, or injected into, another app.
            if hasattr(self.io, "hold_combo") and random.random() < 0.45:
                combo = random.choice(("wa", "wd"))
                actions.append((combo.upper(), lambda k=combo, h=hold: self.io.hold_combo(k, h, should_abort)))
            if random.random() < 0.3:
                actions.append(("SPACE", lambda: self.io.press_key(" ")))
            if random.random() < 0.2:
                actions.append(("LMB", lambda: self.io.click()))
            if random.random() < 0.15:
                actions.append(("RMB", lambda: self.io.right_click()))
            if random.random() < 0.2:
                item = str(random.randint(1, 6))
                actions.append(("ITEM " + item, lambda k=item: self.io.press_key(k)))
            if random.random() < 0.2:
                dx, dy = random.randint(-12, 12), random.randint(-12, 12)
                actions.append(("MOUSE", lambda x=dx, y=dy: self.io.move_mouse(x, y)))
        name, action = random.choice(actions)
        try:
            if not should_abort():
                action()
                if not should_abort():
                    self.last_input = name
                    self.last_input_at = time.monotonic()
                    self.input_count += 1
                    self.last_input_error = ""
                    self.log("log.afk", key=name, sec=f"{hold:.2f}" if name in ("W", "A", "S", "D", "WA", "WD") else "0.07")
        except Exception as exc:
            self.last_input_error = repr(exc)
            self.log("log.error", err="input " + repr(exc))

    def _scan_reward(self, match: tuple[float, tuple[int, int], Template] | None, now: float) -> bool:
        """Count rising edge only. Brief disappearances do not count as another popup."""
        seen = bool(match and match[0] >= self.cfg.threshold)
        if seen:
            self._reward_absent_since = None
            if not self._reward_visible:
                self._reward_visible = True
                if now - self._last_reward >= 8.0:
                    self._last_reward = now
                    self.rewards += 1
                    self.log("log.reward_detected", name=match[2].name, n=self.rewards)
                    if self.on_reward:
                        try:
                            self.on_reward()
                        except Exception as exc:
                            self.log("log.error", err="reward save " + repr(exc))
        elif self._reward_visible:
            if self._reward_absent_since is None:
                self._reward_absent_since = now
            elif now - self._reward_absent_since >= 1.5:
                self._reward_visible = False
                self._reward_absent_since = None
        return seen

    def _afk_wait(self) -> float:
        return max(1.0, self.cfg.afk_interval * random.uniform(0.7, 1.3))

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._paused.is_set():
                self._stop.wait(0.1)
                continue
            t0 = time.monotonic()
            try:
                self._tick()
            except Exception as exc:  # keep the loop alive
                self.log("log.error", err=repr(exc))
                self._stop.wait(1.0)
            self._stop.wait(max(0.0, self.cfg.scan_interval - (time.monotonic() - t0)))
        # fold the running time in when the loop exits
        if not self._paused.is_set():
            self._run_seconds += time.monotonic() - self._tick_mark

    def _tick(self) -> None:
        cfg = self.cfg
        if cfg.require_foreground and not self.io.game_in_foreground():
            if cfg.auto_focus:
                self.io.focus_game()
                self._stop.wait(0.3)
            if not self.io.game_in_foreground():
                self.state = "waiting_window"
                self.score = 0.0
                return

        if not self.templates:
            # New installations have no button images: don't waste time and CPU
            # capturing the screen just to perform a simple keyboard action.
            self.state = "afk_only"
            now = time.monotonic()
            if cfg.afk_enabled and cfg.afk_keys and now >= self._next_afk:
                self._afk_actions(lambda: self._stop.is_set() or self._paused.is_set() or
                                  (cfg.require_foreground and not self.io.game_in_foreground()))
                self._next_afk = time.monotonic() + self._afk_wait()
            return

        frame = self.io.grab()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        best = None
        reward_match = None
        for tpl in self.templates:
            score, pos = best_match(gray, tpl.gray, cfg.scales)
            if tpl.role == "reward":
                if reward_match is None or score > reward_match[0]:
                    reward_match = (score, pos, tpl)
            elif best is None or score > best[0]:
                best = (score, pos, tpl)
        self.score = max(0.0, best[0] if best else (reward_match[0] if reward_match else 0.0))

        now = time.monotonic()
        reward_visible = self._scan_reward(reward_match, now)
        if best and best[0] >= cfg.threshold and best[2].role == "wait":
            self.state = "loading"  # loading / connecting screen: wait quietly
            self._next_afk = now + self._afk_wait()
            return
        if best and best[0] >= cfg.threshold:
            # If focus changes during image matching, never click a different app.
            if cfg.require_foreground and not self.io.game_in_foreground():
                self.state = "waiting_window"
                return
            if now - self._last_click < cfg.click_delay:
                self.state = "button_waiting"
                return
            x = best[1][0] + random.randint(-3, 3)
            y = best[1][1] + random.randint(-3, 3)
            self.io.click(x, y)
            self._last_click = now
            self._next_afk = now + self._afk_wait()
            tpl = best[2]
            if tpl.role == "start":
                self.games += 1
                self.game_times.append(time.time())
                self._in_match = True
                self._result_seen = False
                self.state = "starting"
            else:
                if self._in_match and not self._result_seen:
                    self.cycles += 1
                    self.cycle_times.append(time.time())
                    self._result_seen = True
                self._in_match = False
                self.state = "results"
            self.log("log.clicked", name=tpl.name, score=f"{best[0]:.2f}", x=x, y=y)
            return

        if reward_visible:
            self.state = "reward_visible"
            self._next_afk = now + self._afk_wait()
            return
        # no known button on screen -> we are in a match (or somewhere unknown)
        self.state = "in_match" if self._in_match else "idle"
        if cfg.afk_enabled and cfg.afk_keys and now >= self._next_afk:
            def abort() -> bool:
                return (self._stop.is_set() or self._paused.is_set() or
                        (cfg.require_foreground and not self.io.game_in_foreground()))
            self._afk_actions(abort)
            self._next_afk = time.monotonic() + self._afk_wait()
