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
from replay_detect import yellow_replay_button

# Template file names are "<role>_<anything>.png".
#   start_*  : button that begins the next match (counts a game)
#   result_* : any button on result / reward screens (continue, claim all, back to lobby)
#   wait_*   : a loading / "connecting" screen - nothing is clicked and anti-AFK stays quiet
ROLES = ("start", "result", "wait", "reward", "replay", "death")


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
    auto_launch_game: bool = True    # request Epic Launcher to start Fortnite if not running
    # Configurable global start/stop/pause keys; F6 and F9 remain reserved.
    hotkey_start: str = "F7"
    hotkey_stop: str = "F8"
    hotkey_pause: str = "F10"
    afk_enabled: bool = True
    afk_extra_enabled: bool = False  # opt in to jumps/clicks/item swaps
    afk_interval: float = 6.0       # seconds between anti-AFK presses
    afk_hold: float = 3.0           # max seconds a key is held
    afk_keys: str = "wasd"
    # Randomised, interruptible sequence of ordinary game inputs. Does not bypass anti-cheat.
    afk_sequence_enabled: bool = True
    afk_jump_enabled: bool = True
    afk_sprint_enabled: bool = True
    afk_slide_enabled: bool = True
    afk_camera_enabled: bool = True
    afk_slot_enabled: bool = True
    afk_pickaxe_enabled: bool = False  # optional LMB; may interact with game objects
    afk_grenade_enabled: bool = False  # optional Y + LMB
    afk_weapon_enabled: bool = False   # optional bounded bursts; no ammo OCR
    afk_pause_min: float = 0.5
    afk_pause_max: float = 2.0
    afk_camera_pixels_360: float = 1500.0  # calibrate for player's game sensitivity
    afk_replay_auto_detect: bool = True  # conservative yellow-button detection, no OCR


    @classmethod
    def load(cls, path: Path) -> "Config":
        cfg = cls()
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            names = {f.name for f in fields(cls)}
            for k, v in data.items():
                if k in names:
                    setattr(cfg, k, v)
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        # A damaged or hand-edited config must never crash the global hotkeys.
        default_keys = ("F7", "F8", "F10")
        keys = [getattr(cfg, k) for k in ("hotkey_start", "hotkey_stop", "hotkey_pause")]
        reserved = {"F6", "F9"}
        valid_keys = {f"F{i}" for i in range(1, 13)} - reserved
        if any(not isinstance(k, str) or k not in valid_keys for k in keys) or len(set(keys)) != 3:
            cfg.hotkey_start, cfg.hotkey_stop, cfg.hotkey_pause = default_keys
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


def best_match(frame_gray: np.ndarray, tpl: np.ndarray, scales,
               should_abort: Callable[[], bool] | None = None) -> tuple[float, tuple[int, int]]:
    """Return (score, (cx, cy)) of the best multi-scale match."""
    best = (-1.0, (0, 0))
    fh, fw = frame_gray.shape[:2]
    for s in scales:
        if should_abort is not None and should_abort():
            break
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
        self._awaiting_replay = False
        self._next_afk = 0.0
        self.last_input = ""
        self.last_input_at = 0.0
        self.input_count = 0
        self.last_input_error = ""
        self._last_afk_type = ""
        self._last_slot = 0
        self.wait_reason = ""
        self.probe_status = "idle"
        self.probe_detail = ""
        self.probe_at = ""
        self.probe_target = ""
        self._probe_lock = threading.Lock()
        # Screen capture and OpenCV must NEVER block the control loop.
        # A single daemon analysis job can outlive a stop, but it never sends inputs.
        self._screen_job: dict | None = None
        self._screen_epoch = 0
        # Track Alt+Tab without changing the manual Pause state.
        self._focus_suspended = False
        self._focus_suspended_at = 0.0
        self.focus_result = ""
        self._restart_pending = False
        self.replay_count = 0
        self.replay_source = ""
        self.replay_attempts = 0
        self.replay_status = "idle"
        self._replay_candidate_hits = 0
        self._replay_candidate_pos: tuple[int, int] | None = None
        self._replay_pending = False
        self._replay_absent_frames = 0
        self._replay_missing_frames = 0
        self._death_latched = False
        self._replay_clicked_at = 0.0
        self._replay_last_attempt = 0.0

    # ---- public controls (thread safe)
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def stopping(self) -> bool:
        """Stop request is authoritative even before a slow screen grab finishes."""
        return self.running and self._stop.is_set()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def focus_suspended(self) -> bool:
        return self._focus_suspended and self.running and not self.paused

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
            if self._stop.is_set():
                # F7 immediately after F8 is queued, not silently discarded.
                self._restart_pending = True
                self.log("log.restart_queued")
            elif self.paused:
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
        self._screen_epoch += 1
        self._stop.clear()
        self._paused.clear()
        self._tick_mark = time.monotonic()
        self._next_afk = time.monotonic() + min(0.7, self._afk_wait())
        self.state = "starting"
        self.last_input_error = ""
        self.wait_reason = ""
        self._reward_visible = False
        self._reward_absent_since = None
        self._awaiting_replay = False
        self._replay_pending = False
        self._replay_candidate_hits = 0
        self._replay_candidate_pos = None
        self._replay_absent_frames = 0
        self._replay_missing_frames = 0
        self._death_latched = False
        self.replay_attempts = 0
        self.replay_status = "idle"
        self._focus_suspended = False
        self._focus_suspended_at = 0.0
        self.focus_result = ""
        self._restart_pending = False
        self._thread = threading.Thread(target=self._loop, name="engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Request a stop immediately; long template recognition must not freeze UI.

        A slow Windows capture/OpenCV call may still be in progress. It will
        finish on the worker thread and acknowledge the stop; starting another
        concurrent worker during this phase is forbidden.
        """
        thread = self._thread
        self._restart_pending = False
        if thread is None or not thread.is_alive():
            self.state = "stopped"
            return
        self._stop.set()
        self._screen_epoch += 1
        self._restart_pending = False
        self.state = "stopping"
        if thread is threading.current_thread():
            return
        thread.join(timeout=0.35)
        # _loop's finally clause marks the engine stopped and logs exactly once.

    def toggle_pause(self) -> None:
        if not self.running or self._stop.is_set():
            return
        self._screen_epoch += 1  # Never reuse a pre-pause screenshot after resuming.
        if self.paused:
            self._tick_mark = time.monotonic()
            self._paused.clear()
            self.log("log.resumed")
        else:
            self._run_seconds += time.monotonic() - self._tick_mark
            self._paused.set()
            self.state = "paused"
            self.log("log.paused")

    def input_probe(self, target: str = "fortnite") -> dict:
        """Deliberate, bounded diagnostic. Never sends to an unexpected app.

        Windows SendInput success only means the OS accepted the event, not
        that a protected game processed it. Notepad can confirm normal typing.
        """
        if not self._probe_lock.acquire(blocking=False):
            return {"status": "busy", "detail": "A test is already running"}
        try:
            self.probe_at = time.strftime("%H:%M:%S")
            self.probe_target = target
            if target not in ("fortnite", "notepad"):
                self.probe_status = "error"
                self.probe_detail = "Unknown test target"
            elif self.running:
                self.probe_status = "busy"
                self.probe_detail = "Stop Anti-AFK before testing"
            else:
                def ready() -> bool:
                    if target == "notepad":
                        return (hasattr(self.io, "foreground_process") and
                                self.io.foreground_process().lower() == "notepad.exe")
                    return self.io.game_in_foreground()
                if not ready():
                    self.probe_status = "waiting_window"
                    self.probe_detail = f"{target} is not the active window"
                else:
                    try:
                        if target == "notepad":
                            self.io.press_key("w")
                        elif hasattr(self.io, "hold_keys"):
                            self.io.hold_keys(("w",), 0.30, lambda: not ready())
                        else:
                            self.io.hold_key("w", 0.30, lambda: not ready())
                        if ready():
                            self.probe_status = "sent"
                            self.probe_detail = f"Windows accepted W input; check {target} visually"
                        else:
                            self.probe_status = "waiting_window"
                            self.probe_detail = f"{target} lost focus during test"
                    except Exception as exc:
                        self.probe_status = "error"
                        self.probe_detail = repr(exc)
            self.log("log.probe_result", status=self.probe_status, detail=self.probe_detail)
            return {"status": self.probe_status, "detail": self.probe_detail}
        finally:
            self._probe_lock.release()

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

    def _smart_afk_action(self, should_abort: Callable[[], bool]) -> None:
        """One weighted action; every IO operation must be abortable and release keys.

        Does not infer ammo, item ownership, death or game state. Detection is
        handled by optional screen templates in _tick(), never by guessing.
        """
        cfg = self.cfg
        if not cfg.afk_enabled or should_abort():
            return
        eligible: list[tuple[str, int]] = [("move", 34)]
        if hasattr(self.io, "hold_keys"):
            eligible.append(("crouch", 4))
        if cfg.afk_jump_enabled and hasattr(self.io, "hold_keys"):
            eligible.append(("jump", 10))
        if cfg.afk_sprint_enabled and hasattr(self.io, "hold_keys"):
            eligible.extend((("sprint", 15), ("sprint_jump", 10) if cfg.afk_jump_enabled else ("sprint", 5)))
        if cfg.afk_slide_enabled and cfg.afk_sprint_enabled and hasattr(self.io, "hold_keys"):
            eligible.append(("slide", 10))
            if cfg.afk_jump_enabled:
                eligible.append(("slide_jump", 6))
        if cfg.afk_camera_enabled and hasattr(self.io, "move_mouse_relative"):
            eligible.extend((("yaw", 10), ("pitch", 8)))
        if cfg.afk_slot_enabled and hasattr(self.io, "press_key"):
            eligible.append(("slot", 7))
        if cfg.afk_pickaxe_enabled and hasattr(self.io, "hold_mouse"):
            eligible.append(("pickaxe", 3))
        if cfg.afk_grenade_enabled and hasattr(self.io, "hold_mouse") and hasattr(self.io, "press_key"):
            eligible.append(("grenade", 2))
        if cfg.afk_weapon_enabled and hasattr(self.io, "aim_and_fire") and hasattr(self.io, "press_key"):
            eligible.append(("weapon", 2))
        # Avoid identical consecutive actions, not claim of anti-detection.
        choices = [(name, weight) for name, weight in eligible if name != self._last_afk_type]
        if not choices:
            choices = eligible
        action = random.choices([n for n, _ in choices], weights=[w for _, w in choices], k=1)[0]
        hold_cap = max(.3, min(4.0, float(cfg.afk_hold)))
        hold = random.uniform(.3, hold_cap)
        label = action.upper()

        def keys(*items: str, duration: float = hold) -> None:
            # Old third-party IO stubs can keep movement support, but extended
            # inputs require the new WinIO.hold_keys API.
            if hasattr(self.io, "hold_keys"):
                self.io.hold_keys(items, duration, should_abort)
            elif len(items) == 1 and items[0] in "wasd":
                self.io.hold_key(items[0], duration, should_abort)
            elif all(k in "wasd" for k in items) and hasattr(self.io, "hold_combo"):
                self.io.hold_combo("".join(items), duration, should_abort)
            else:
                raise RuntimeError("Update winio.py for extended anti-AFK actions")

        try:
            if action == "move":
                directions = ["w", "a", "s", "d", "wa", "wd", "sa", "sd"]
                available = [d for d in directions if all(k in cfg.afk_keys for k in d) and
                             (len(d) == 1 or hasattr(self.io, "hold_keys") or hasattr(self.io, "hold_combo"))]
                if not available:
                    available = ["w"]
                direction = random.choice(available)
                keys(*direction)
                label = "+".join(k.upper() for k in direction)
            elif action == "crouch":
                keys("ctrl", duration=random.uniform(.35, 1.3)); label = "CTRL"
            elif action == "jump":
                keys("space", duration=random.uniform(.1, .3)); label = "SPACE"
            elif action == "sprint":
                keys("w", "shift"); label = "W+SHIFT"
            elif action == "sprint_jump":
                keys("w", "shift", "space"); label = "W+SHIFT+SPACE"
            elif action == "slide":
                if hasattr(self.io, "slide_sequence"):
                    self.io.slide_sequence(hold, False, should_abort)
                else:
                    keys("w", "shift", "ctrl")  # legacy injected IO adapters
                label = "SPRINT → SLIDE"
            elif action == "slide_jump":
                if hasattr(self.io, "slide_sequence"):
                    self.io.slide_sequence(hold, True, should_abort)
                else:
                    keys("w", "shift", "ctrl", "space")  # legacy IO adapters
                label = "SPRINT → SLIDE → JUMP"
            elif action == "yaw":
                angle = random.randint(25, 360)
                direction = random.choice((-1, 1))
                px = round(float(cfg.afk_camera_pixels_360) * angle / 360) * direction
                self.io.move_mouse_relative(px, 0, random.uniform(.2, 1.5), should_abort)
                label = f"CAM {'R' if direction > 0 else 'L'} {angle}°"
            elif action == "pitch":
                angle = random.choice((45, 90, 90, 180))
                direction = random.choice((-1, 1))
                # Relative mouse travel is only an approximation of degrees;
                # pitch clamping means the return can be imperfect.
                px = round(float(cfg.afk_camera_pixels_360) * angle / 360)
                self.io.move_mouse_relative(0, px * direction, random.uniform(.2, .65), should_abort)
                if not should_abort():
                    time.sleep(.08)
                    self.io.move_mouse_relative(0, -px * direction, random.uniform(.2, .65), should_abort)
                label = f"CAM {'DOWN' if direction > 0 else 'UP'} {angle}° + CENTER"
            elif action == "slot":
                slots = [n for n in range(1, 7) if n != self._last_slot]
                self._last_slot = random.choice(slots)
                self.io.press_key(str(self._last_slot))
                label = f"SLOT {self._last_slot}"
            elif action == "pickaxe":
                # Only clicks when the user explicitly enables the action.
                self.io.hold_mouse("left", random.uniform(.12, .7), should_abort)
                label = "PICKAXE LMB"
            elif action == "grenade":
                self.io.press_key("y")
                if not should_abort():
                    self.io.hold_mouse("left", random.uniform(.08, .2), should_abort)
                label = "Y + LMB"
            elif action == "weapon":
                self.io.press_key("2")
                if not should_abort():
                    # Ammo count recognition is not implemented. Hard cap burst.
                    self.io.aim_and_fire(random.uniform(.35, 1.5), should_abort)
                label = "SLOT 2 + RMB + LMB (BOUNDED)"
            if should_abort():
                return
            self.last_input = label
            self._last_afk_type = action
            self.last_input_at = time.monotonic()
            self.input_count += 1
            self.last_input_error = ""
            self.log("log.afk_action", action=label)
        except Exception as exc:
            self.last_input_error = repr(exc)
            self.log("log.error", err="smart AFK: " + repr(exc))

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
        if self.cfg.afk_sequence_enabled:
            lo = max(.2, float(self.cfg.afk_pause_min))
            hi = max(lo, float(self.cfg.afk_pause_max))
            return random.uniform(lo, hi)
        return max(1.0, self.cfg.afk_interval * random.uniform(0.7, 1.3))

    def _run_afk_if_due(self, now: float) -> None:
        cfg = self.cfg
        if not cfg.afk_enabled or now < self._next_afk:
            return
        def abort() -> bool:
            return (self._stop.is_set() or self._paused.is_set() or
                    ((cfg.require_foreground or cfg.afk_sequence_enabled) and
                     not self.io.game_in_foreground()))
        if cfg.afk_sequence_enabled:
            self._smart_afk_action(abort)
        else:
            self._afk_actions(abort)
        self._next_afk = time.monotonic() + self._afk_wait()


    def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                if self._paused.is_set():
                    self._stop.wait(0.1)
                    continue
                t0 = time.monotonic()
                try:
                    self._tick()
                except Exception as exc:
                    self.last_input_error = repr(exc)
                    self.log("log.error", err=repr(exc))
                    self._stop.wait(1.0)
                self._stop.wait(max(0.0, self.cfg.scan_interval - (time.monotonic() - t0)))
        finally:
            if not self._paused.is_set():
                self._run_seconds += time.monotonic() - self._tick_mark
            self.state = "stopped"
            self.wait_reason = ""
            self.log("log.stopped")
            if self._restart_pending:
                # Wait for the old worker to *fully* exit before starting a new one.
                old_thread = threading.current_thread()
                threading.Thread(target=self._restart_after, args=(old_thread,),
                                 name="engine-restart", daemon=True).start()

    def _restart_after(self, old_thread: threading.Thread) -> None:
        old_thread.join(timeout=20)
        if not old_thread.is_alive() and self._restart_pending:
            self._restart_pending = False
            self.start()

    def _record_replay_click(self, position: tuple[int, int], now: float, source: str) -> bool:
        """Click only the replay candidate, with a strict foreground re-check."""
        if self._stop.is_set() or self._paused.is_set() or not self.io.game_in_foreground():
            self.state = "waiting_window"
            return False
        x, y = position
        self.io.click(x, y)
        self._last_click = now
        self._replay_last_attempt = now
        self.replay_attempts += 1
        self.replay_source = source
        self._replay_pending = True
        self._awaiting_replay = False
        self._death_latched = False
        self._replay_missing_frames = 0
        self._replay_absent_frames = 0
        if self.replay_attempts == 1:
            self._replay_clicked_at = now
            self.replay_count += 1
            self.games += 1
            self.game_times.append(time.time())
            self._in_match = False  # not in a match until the button disappears
            self._result_seen = False
        self.state = "loading"
        self.replay_status = "clicked"
        self._next_afk = now + 8.0
        self.log("log.replay_clicked", source=source, attempt=self.replay_attempts)
        return True

    def _capture_and_match(self, templates: tuple[Template, ...], scales: tuple[float, ...],
                           scan_yellow: bool, epoch: int) -> tuple:
        """Pure screen analysis. May run slowly, but NEVER clicks or presses keys."""
        frame = self.io.grab()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if templates else None
        best = reward_match = replay_match = death_match = None
        for tpl in templates:
            if self._stop.is_set() or epoch != self._screen_epoch:
                break
            score, pos = best_match(
                gray, tpl.gray, scales,
                lambda: self._stop.is_set() or epoch != self._screen_epoch)
            match = (score, pos, tpl)
            if tpl.role == "reward":
                if reward_match is None or score > reward_match[0]:
                    reward_match = match
            elif tpl.role == "replay":
                if replay_match is None or score > replay_match[0]:
                    replay_match = match
            elif tpl.role == "death":
                if death_match is None or score > death_match[0]:
                    death_match = match
            elif best is None or score > best[0]:
                best = match
        yellow = yellow_replay_button(frame) if scan_yellow and not (
            replay_match and replay_match[0] >= self.cfg.threshold) and not (
                self._stop.is_set() or epoch != self._screen_epoch) else None
        return frame.shape, best, reward_match, replay_match, death_match, yellow

    def _read_screen_without_blocking_controls(self, templates: tuple[Template, ...],
                                               scan_yellow: bool) -> tuple | None:
        """Return the last completed frame or None; cancellation is always responsive.

        The analysis is confined to at most ONE daemon worker, even if ImageGrab
        stalls permanently. A newly started session never consumes an old frame.
        """
        job = self._screen_job
        epoch = self._screen_epoch
        if job is not None and job["epoch"] != epoch:
            if job["done"].is_set():
                self._screen_job = job = None  # Discard a pre-stop/pause frame.
            else:
                self.wait_reason = "capture_slow"
                return None
        if job is None:
            job = {"epoch": epoch, "started": time.monotonic(),
                   "done": threading.Event(), "value": None, "error": None}
            self._screen_job = job
            scales = tuple(self.cfg.scales)
            def analyze():
                try:
                    job["value"] = self._capture_and_match(templates, scales, scan_yellow, epoch)
                except Exception as exc:
                    job["error"] = exc
                finally:
                    job["done"].set()
            threading.Thread(target=analyze, daemon=True, name="screen-analysis").start()
        # 0.20 s at most; frequently check F8 and pause while OpenCV works.
        for _ in range(10):
            if self._stop.is_set() or self._paused.is_set():
                return None
            if job["done"].wait(.02):
                break
        if not job["done"].is_set():
            if time.monotonic() - job["started"] >= 3.0:
                self.wait_reason = "capture_slow"
            return None
        self._screen_job = None
        if self._stop.is_set() or self._paused.is_set() or job["epoch"] != self._screen_epoch:
            return None
        if job["error"] is not None:
            raise job["error"]
        return job["value"]

    def _tick(self) -> None:
        if self._stop.is_set() or self._paused.is_set():
            return
        cfg = self.cfg
        foreground_required = cfg.require_foreground or cfg.afk_sequence_enabled
        if foreground_required and not self.io.game_in_foreground():
            # Auto-suspend on Alt+Tab; never steal focus from other apps.
            if not self._focus_suspended:
                self._focus_suspended = True
                self._focus_suspended_at = time.monotonic()
                self._screen_epoch += 1  # invalidate pre-Alt+Tab frame
                self._replay_candidate_hits = 0
                self._replay_candidate_pos = None
                self.log("log.focus_suspended")
            found = self.io.game_window_found() if hasattr(self.io, "game_window_found") else False
            self.wait_reason = "not_foreground" if found else "not_found"
            self.state = "waiting_window"
            self.score = 0.0
            return
        if self._focus_suspended:
            self._focus_suspended = False
            self._screen_epoch += 1
            # Let Fortnite settle before sending another movement on return.
            self._next_afk = max(self._next_afk, time.monotonic() + .65)
            self._replay_candidate_hits = 0
            self._replay_candidate_pos = None
            self.log("log.focus_resumed")
        self.wait_reason = ""
        has_templates = bool(self.templates)
        scan_yellow = bool(cfg.afk_enabled and cfg.afk_replay_auto_detect)
        if not has_templates and not scan_yellow:
            if not cfg.afk_enabled:
                self.state = "afk_disabled"
                self.wait_reason = "afk_disabled"
                return
            self.state = "afk_only"
            self._run_afk_if_due(time.monotonic())
            return
        if not hasattr(self.io, "grab"):
            # Some test/external IO adapters have keyboard support but no screen capture.
            self.state = "afk_only"
            self._run_afk_if_due(time.monotonic())
            return
        analysis = self._read_screen_without_blocking_controls(tuple(self.templates), scan_yellow)
        if self._stop.is_set() or self._paused.is_set():
            return
        if analysis is None:
            # Keep AFK input alive when screenshot capture is slow, provided
            # Fortnite is STILL foreground. Never click an unverified frame.
            self.state = "capture_waiting"
            self._run_afk_if_due(time.monotonic())
            return
        frame_shape, best, reward_match, replay_match, death_match, yellow_found = analysis
        self.wait_reason = ""
        now = time.monotonic()
        # A saved replay template takes precedence; the yellow-button shape is
        # a conservative built-in fallback with 3-frame confirmation.
        replay_position = None
        replay_source = ""
        replay_score = 0.0
        if replay_match and replay_match[0] >= cfg.threshold:
            replay_position, replay_score, replay_source = replay_match[1], replay_match[0], "template"
        elif scan_yellow:
            found = yellow_found
            if found is not None:
                replay_score, replay_position = found
                replay_source = "yellow"
        death_visible = bool(death_match and death_match[0] >= cfg.threshold)
        self.score = max(0.0, replay_score, best[0] if best else 0.0)

        # After clicking replay, hold all anti-AFK inputs until we actually
        # leave the results screen and a short loading period has elapsed.
        if self._replay_pending:
            if replay_position is not None:
                self._replay_absent_frames = 0
                if now - self._replay_last_attempt >= 6.0:
                    if self.replay_attempts < 3:
                        self._record_replay_click(replay_position, now, replay_source)
                    else:
                        self.replay_status = "unresponsive"
                        self.wait_reason = "replay_unresponsive"
                        self.state = "await_replay"
                else:
                    self.state = "loading"
            else:
                self._replay_absent_frames += 1
                if self._replay_absent_frames >= 2 and not death_visible and now - self._replay_clicked_at >= 6.0:
                    self._replay_pending = False
                    self.replay_attempts = 0
                    self.replay_status = "resumed"
                    self._in_match = True
                    self.state = "in_match"
                    self._next_afk = now + .5
                    self.log("log.replay_resumed")
                else:
                    self.state = "loading"
            return

        # The right-side yellow button can be recognised without the '#5'
        # position text and without a manually saved image.
        if replay_position is not None:
            self._awaiting_replay = True
            self._replay_missing_frames = 0
            self._in_match = False
            self._next_afk = now + 1.0
            self.replay_status = "seen"
            if self._replay_candidate_pos is not None and \
               abs(replay_position[0]-self._replay_candidate_pos[0]) < max(25, frame_shape[1] * .04) and \
               abs(replay_position[1]-self._replay_candidate_pos[1]) < max(20, frame_shape[0] * .04):
                self._replay_candidate_hits += 1
            else:
                self._replay_candidate_hits = 1
            self._replay_candidate_pos = replay_position
            # A user-captured replay template is exact; colour-only detection
            # requires confirmation on 3 consecutive frames.
            confirmation = 1 if replay_source == "template" else 3
            if self._replay_candidate_hits < confirmation or now - self._last_click < cfg.click_delay:
                self.state = "await_replay"
                return
            self._record_replay_click(replay_position, now, replay_source)
            return
        self._replay_candidate_hits = 0
        self._replay_candidate_pos = None
        if death_visible:
            self._awaiting_replay = True
            self._death_latched = True
            self._in_match = False
            self.replay_status = "death"
        if self._awaiting_replay:
            # A single false positive yellow rectangle should not freeze AFK
            # forever. An explicit death template, however, holds the latch.
            if not self._death_latched:
                self._replay_missing_frames += 1
                if self._replay_missing_frames >= 3:
                    self._awaiting_replay = False
                    self.replay_status = "idle"
            if self._awaiting_replay:
                self.state = "await_replay"
                self._next_afk = now + 1.0
                return

        reward_visible = self._scan_reward(reward_match, now)
        if best and best[0] >= cfg.threshold and best[2].role == "wait":
            self.state = "loading"
            self._next_afk = now + self._afk_wait()
            return
        if best and best[0] >= cfg.threshold:
            if foreground_required and not self.io.game_in_foreground():
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
        self.state = "in_match" if self._in_match else ("afk_only" if cfg.afk_enabled and not has_templates else "idle")
        self._run_afk_if_due(now)
