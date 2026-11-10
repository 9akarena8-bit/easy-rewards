"""Easy Rewards - screen-recognition automation panel (Windows, Python 3.10+).

Run:  python app.py          (GUI)
      python app.py --cli    (headless, F7 start / F8 stop / F10 pause)
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import messagebox

import cv2

import updater
from core import Config, Engine, ROLES, best_match, load_templates
from i18n import tr

try:  # importing winio first also makes the process DPI-aware before Tk starts
    from winio import WinIO, HotkeyPoller
except ImportError:
    if sys.platform == "win32":
        raise  # a missing package (e.g. Pillow) - let the real error show up
    WinIO = HotkeyPoller = None  # not Windows

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"
TEMPLATES = BASE / "templates"
ASSETS = BASE / "assets"
FONT = "Segoe UI"
CRASH_LOG = BASE / "crash.log"


def write_crash(exc_type, exc, tb) -> str:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n{text}")
    except OSError:
        pass
    return text

# Soft pastel palettes (warm light / dusky dark - no pure black or white glare).
PALETTES = {
    "light": dict(bg="#fbf7f2", side="#f5eee5", card="#ffffff", card_border="#f0e7db",
                  fg="#3d3548", muted="#8f8799", accent="#f4b968", accent_hover="#efa94f",
                  accent_fg="#4a3213", soft="#f6efe6", soft_hover="#ede2d4", field="#faf5ee",
                  ok="#72c593", warn="#f2b45c", off="#d4cbd9"),
    "dark": dict(bg="#1f1d29", side="#262434", card="#2d2b3c", card_border="#393650",
                 fg="#ece8f4", muted="#9d97af", accent="#f3c27e", accent_hover="#f8cf93",
                 accent_fg="#2f2310", soft="#383551", soft_hover="#434060", field="#242232",
                 ok="#82d3a3", warn="#f3c27e", off="#5c586f"),
}


def rrect(c: tk.Canvas, x1, y1, x2, y2, r, **kw):
    """Rounded rectangle on a canvas."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


# ------------------------------------------------------------ widgets
class Frm(tk.Frame):
    def __init__(self, parent, app, surface="bg", **kw):
        super().__init__(parent, bd=0, highlightthickness=0, **kw)
        self.app, self.surface = app, surface
        app.reg(self)

    def restyle(self):
        self.configure(bg=self.app.c[self.surface])


class Lbl(tk.Label):
    def __init__(self, parent, app, key=None, text="", kind="fg", size=10, bold=False,
                 surface="bg", wrap=0, **kw):
        super().__init__(parent, bd=0, text=text, anchor=kw.pop("anchor", "w"),
                         justify=kw.pop("justify", "left"), wraplength=app.px(wrap) if wrap else 0, **kw)
        self.app, self.key, self.kind, self.size, self.bold, self.surface = app, key, kind, size, bold, surface
        self.fmt: dict = {}
        app.reg(self)

    def restyle(self):
        c = self.app.c
        self.configure(bg=c[self.surface], fg=c[self.kind], font=self.app.font(self.size, self.bold))

    def retext(self):
        if self.key:
            self.configure(text=self.app.tr(self.key, **self.fmt))


class Pill(tk.Canvas):
    """Rounded button. kinds: primary | soft | chip (selectable) | nav (selectable)."""

    def __init__(self, parent, app, key=None, text="", command=None, kind="soft", surface="card",
                 height=38, padx=20, radius=None, size=10, bold=False, anchor="center",
                 stretch=False, minw=0):
        super().__init__(parent, highlightthickness=0, bd=0, width=app.px(10), height=app.px(height),
                         cursor="hand2")
        self.app, self.key, self.command, self.kind, self.surface = app, key, command, kind, surface
        self.padx, self.radius, self.size, self.bold = padx, radius, size, bold
        self.anchor, self.stretch, self.minw = anchor, stretch, minw
        self.selected = False
        self._hover = False
        self._text = text
        self._reqw = app.px(100)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", self._click)
        self.bind("<Configure>", lambda e: self._draw())
        app.reg(self)

    def retext(self):
        if self.key:
            self._text = self.app.tr(self.key)
        self._fit()
        self._draw()

    def set_key(self, key):
        if key != self.key:
            self.key = key
            self.retext()

    def set_selected(self, flag: bool):
        self.selected = flag
        self._draw()

    def restyle(self):
        self.configure(bg=self.app.c[self.surface])
        self._fit()
        self._draw()

    def _fit(self):
        if not self.stretch:
            f = tkfont.Font(family=FONT, size=self.size, weight="bold" if self.bold else "normal")
            self._reqw = max(self.app.px(self.minw), f.measure(self._text) + 2 * self.app.px(self.padx))
            self.configure(width=self._reqw)

    def _set_hover(self, flag):
        self._hover = flag
        self._draw()

    def _click(self, _e):
        if self.command:
            self.command()

    def _colors(self):
        c, k, h = self.app.c, self.kind, self._hover
        if k == "primary":
            return (c["accent_hover"] if h else c["accent"]), c["accent_fg"], None
        if k == "chip":
            if self.selected:
                return c["accent"], c["accent_fg"], None
            off = c["card"] if self.surface == "side" else c["soft"]  # keep chips visible on the sidebar
            return (c["soft_hover"] if h else off), c["fg"], None
        if k == "nav":
            if self.selected:
                return c["card"], c["fg"], c["card_border"]
            return (c["soft_hover"] if h else None), c["muted"], None
        return (c["soft_hover"] if h else c["soft"]), c["fg"], None

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        if w <= 1:
            w = self._reqw
        h = self.winfo_height()
        if h <= 1:
            h = int(float(self.cget("height")))
        fill, fg, border = self._colors()
        r = self.radius if self.radius is not None else h / 2
        if fill:
            rrect(self, 1, 1, w - 1, h - 1, self.app.px(r) if self.radius is not None else r,
                  fill=fill, outline=border or fill)
        if self.kind == "nav" and self.selected:
            d = self.app.px(4)
            cx = self.app.px(16)
            self.create_oval(cx - d, h / 2 - d, cx + d, h / 2 + d, fill=self.app.c["accent"], outline="")
        font = self.app.font(self.size, self.bold)
        if self.anchor == "center":
            self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=font)
        else:
            self.create_text(self.app.px(self.padx), h / 2, text=self._text, fill=fg, font=font, anchor="w")


class Segmented(Frm):
    def __init__(self, parent, app, options, value, command, surface="card"):
        super().__init__(parent, app, surface)
        self.command = command
        self.buttons: dict[str, Pill] = {}
        for val, text, key in options:
            b = Pill(self, app, key=key, text=text, kind="chip", surface=surface, height=32, padx=13,
                     size=9, bold=True, command=lambda v=val: self._pick(v))
            b.pack(side="left", padx=(0, 6))
            self.buttons[val] = b
        self.set(value)

    def set(self, value):
        for v, b in self.buttons.items():
            b.set_selected(v == value)

    def _pick(self, value):
        self.set(value)
        self.command(value)


class Toggle(tk.Canvas):
    def __init__(self, parent, app, variable, surface="card"):
        self.app, self.var, self.surface = app, variable, surface
        self._w, self._h = app.px(46), app.px(26)
        super().__init__(parent, width=self._w, height=self._h, highlightthickness=0, bd=0, cursor="hand2")
        self.bind("<Button-1>", lambda e: self.var.set(not self.var.get()))
        self.var.trace_add("write", lambda *a: self._draw())
        app.reg(self)

    def restyle(self):
        self.configure(bg=self.app.c[self.surface])
        self._draw()

    def _draw(self):
        c, on = self.app.c, bool(self.var.get())
        self.delete("all")
        w, h = self._w, self._h
        rrect(self, 1, 1, w - 1, h - 1, h / 2, fill=c["accent"] if on else c["off"], outline="")
        r = h / 2 - self.app.px(4)
        cx = w - h / 2 if on else h / 2
        self.create_oval(cx - r, h / 2 - r, cx + r, h / 2 + r, fill="#ffffff", outline="")


class Slider(tk.Canvas):
    def __init__(self, parent, app, variable, lo, hi, surface="card", width=170):
        self.app, self.var, self.lo, self.hi, self.surface = app, variable, lo, hi, surface
        self._w, self._h = app.px(width), app.px(28)
        super().__init__(parent, width=self._w, height=self._h, highlightthickness=0, bd=0, cursor="hand2")
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self.var.trace_add("write", lambda *a: self._draw())
        app.reg(self)

    def _drag(self, e):
        pad = self.app.px(12)
        t = min(1.0, max(0.0, (e.x - pad) / max(1, self._w - 2 * pad)))
        self.var.set(round(self.lo + t * (self.hi - self.lo), 2))

    def restyle(self):
        self.configure(bg=self.app.c[self.surface])
        self._draw()

    def _draw(self):
        c = self.app.c
        self.delete("all")
        pad, h, w = self.app.px(12), self._h, self._w
        t = (float(self.var.get()) - self.lo) / (self.hi - self.lo)
        x = pad + t * (w - 2 * pad)
        th = self.app.px(3)
        rrect(self, pad, h / 2 - th, w - pad, h / 2 + th, th, fill=c["soft_hover"], outline="")
        rrect(self, pad, h / 2 - th, max(pad + 1, x), h / 2 + th, th, fill=c["accent"], outline="")
        r = self.app.px(9)
        self.create_oval(x - r, h / 2 - r, x + r, h / 2 + r, fill="#ffffff", outline=c["accent"], width=2)


class Stepper(Frm):
    def __init__(self, parent, app, variable, lo, hi, step, decimals=1, surface="card"):
        super().__init__(parent, app, surface)
        self.var, self.lo, self.hi, self.step, self.dec = variable, lo, hi, step, decimals
        Pill(self, app, text="−", kind="soft", surface=surface, height=30, padx=0, minw=30, size=12,
             bold=True, command=lambda: self._bump(-1)).pack(side="left")
        self.val = Lbl(self, app, text="", surface=surface, size=10, bold=True, anchor="center", width=6)
        self.val.pack(side="left", padx=4)
        Pill(self, app, text="+", kind="soft", surface=surface, height=30, padx=0, minw=30, size=12,
             bold=True, command=lambda: self._bump(1)).pack(side="left")
        self.var.trace_add("write", lambda *a: self._show())
        self._show()

    def _bump(self, d):
        self.var.set(round(min(self.hi, max(self.lo, float(self.var.get()) + d * self.step)), self.dec))

    def _show(self):
        self.val.configure(text=f"{float(self.var.get()):.{self.dec}f}")


class Field(Frm):
    def __init__(self, parent, app, variable, width=12, surface="card"):
        super().__init__(parent, app, surface)
        self.entry = tk.Entry(self, textvariable=variable, width=width, relief="flat", bd=0, highlightthickness=1)
        self.entry.pack(padx=2, pady=2, ipady=app.px(6), ipadx=app.px(8))

    def restyle(self):
        super().restyle()
        c = self.app.c
        self.entry.configure(bg=c["field"], fg=c["fg"], insertbackground=c["fg"], font=self.app.font(10),
                             highlightbackground=c["card_border"], highlightcolor=c["accent"])


class Dot(tk.Canvas):
    def __init__(self, parent, app, surface="card"):
        self.app, self.surface, self.color_key = app, surface, "off"
        size = app.px(14)
        super().__init__(parent, width=size, height=size, highlightthickness=0, bd=0)
        self._s = size
        app.reg(self)

    def set_color(self, key):
        if key != self.color_key:
            self.color_key = key
            self._draw()

    def restyle(self):
        self.configure(bg=self.app.c[self.surface])
        self._draw()

    def _draw(self):
        self.delete("all")
        c = self.app.c[self.color_key]
        self.create_oval(2, 2, self._s - 2, self._s - 2, fill=c, outline="")


class Card(tk.Canvas):
    """Rounded card. Put content in `.body`; children use surface=card.surf."""

    def __init__(self, parent, app, surface="bg", fill="card", radius=20, pad=18, fixed=False):
        super().__init__(parent, highlightthickness=0, bd=0, width=app.px(10), height=app.px(40))
        self.app, self.parent_surface, self.surf = app, surface, fill
        self.r, self.pad, self.fixed = app.px(radius), app.px(pad), fixed
        self.body = tk.Frame(self, bd=0, highlightthickness=0)
        self._win = self.create_window(self.pad, self.pad, window=self.body, anchor="nw")
        self.bind("<Configure>", self._layout)
        self.body.bind("<Configure>", self._layout)
        app.reg(self)

    def restyle(self):
        c = self.app.c
        self.configure(bg=c[self.parent_surface])
        self.body.configure(bg=c[self.surf])
        self._layout()

    def _layout(self, _e=None):
        w = self.winfo_width()
        if w < 5:
            return
        pad, c = self.pad, self.app.c
        if self.fixed:
            hh = max(10, self.winfo_height())
            self.itemconfigure(self._win, width=max(1, w - 2 * pad), height=max(1, hh - 2 * pad))
        else:
            hh = self.body.winfo_reqheight() + 2 * pad
            if abs(int(float(self.cget("height"))) - hh) > 1:
                self.configure(height=hh)
            self.itemconfigure(self._win, width=max(1, w - 2 * pad))
        self.delete("bg")
        rrect(self, 1, 1, w - 1, hh - 1, self.r, fill=c[self.surf], outline=c["card_border"], tags="bg")
        self.tag_lower("bg")


# ------------------------------------------------------------------ app
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = Config.load(CONFIG_PATH)
        self.io = WinIO()
        self.scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.c = PALETTES.get(self.cfg.theme, PALETTES["light"])
        self.widgets: list = []
        self.logq: "queue.Queue[tuple]" = queue.Queue()
        self.engine = Engine(self.cfg, self.io, TEMPLATES, log=self._log)
        self._tpl_names: list[str] = []
        self.restart_requested = False
        self.pending_update: dict | None = None
        self.upq: "queue.Queue[tuple]" = queue.Queue()
        self.ui_segs: list[Segmented] = []
        self.theme_segs: list[Segmented] = []

        self.title("Easy Rewards")
        self.geometry(f"{self.px(1060)}x{self.px(760)}")
        self.minsize(self.px(960), self.px(700))
        self._load_logo()
        self._build()
        self.show("home")
        self.refresh_all()
        self.refresh_templates()

        if HotkeyPoller:
            HotkeyPoller({"F7": self.engine.start, "F8": self.engine.stop,
                          "F10": self.engine.toggle_pause}).start()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(250, self._tick)
        if self.cfg.auto_update and self.cfg.update_url:
            self.after(4000, lambda: self.check_updates(auto=True))

    # ---- helpers
    def px(self, n) -> int:
        return int(round(n * self.scale))

    def font(self, size=10, bold=False):
        return (FONT, size, "bold") if bold else (FONT, size)

    def tr(self, key, **kw) -> str:
        return tr(self.cfg.ui_language, key, **kw)

    def reg(self, w):
        self.widgets.append(w)
        return w

    def refresh_all(self) -> None:
        self.configure(bg=self.c["bg"])
        for w in self.widgets:
            w.restyle()
            if hasattr(w, "retext"):
                w.retext()
        c = self.c
        self.logbox.configure(bg=c["card"], fg=c["fg"], insertbackground=c["fg"], font=self.font(9),
                              selectbackground=c["soft_hover"])
        self.logbox.tag_configure("ts", foreground=c["muted"])
        self.lst.configure(bg=c["field"], fg=c["fg"], selectbackground=c["soft_hover"],
                           selectforeground=c["fg"], font=self.font(10))
        for page, key in self.nav_keys.items():
            self.nav[page].set_selected(page == self.current)
        self.refresh_templates()

    def _load_logo(self) -> None:
        self.logo = self.icon_img = None
        try:
            name = "logo_88.png" if self.scale >= 1.5 else "logo_44.png"
            self.logo = tk.PhotoImage(file=str(ASSETS / name))
            self.icon_img = tk.PhotoImage(file=str(ASSETS / "logo_256.png"))
            self.iconphoto(True, self.icon_img)
            self.iconbitmap(default=str(ASSETS / "icon.ico"))
        except (tk.TclError, OSError):
            pass

    # ---- layout
    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        m = self.px(16)

        self.side = Card(self, self, surface="bg", fill="side", radius=26, pad=14, fixed=True)
        self.side.configure(width=self.px(236))
        self.side.grid(row=0, column=0, sticky="ns", padx=(m, 0), pady=m)
        self._build_sidebar(self.side.body)

        self.main = Frm(self, self, "bg")
        self.main.grid(row=0, column=1, sticky="nsew", padx=self.px(26), pady=self.px(22))
        self.main.rowconfigure(0, weight=1)
        self.main.columnconfigure(0, weight=1)
        self.pages = {k: Frm(self.main, self, "bg") for k in ("home", "settings", "afk", "templates", "updates")}
        for p in self.pages.values():
            p.grid(row=0, column=0, sticky="nsew")
        self._build_home(self.pages["home"])
        self._build_settings(self.pages["settings"])
        self._build_afk(self.pages["afk"])
        self._build_templates(self.pages["templates"])
        self._build_updates(self.pages["updates"])

    def _build_sidebar(self, b) -> None:
        s = "side"
        brand = Frm(b, self, s)
        brand.pack(fill="x", pady=(6, 20))
        if self.logo:
            Lbl(brand, self, surface=s, image=self.logo).pack(side="left", padx=(4, 10))
        Lbl(brand, self, text="Easy Rewards", size=13, bold=True, surface=s).pack(side="left")

        self.nav, self.nav_keys, self.current = {}, {}, "home"
        for page, key in (("home", "nav.home"), ("settings", "nav.settings"),
                          ("afk", "nav.afk"), ("templates", "nav.templates"),
                          ("updates", "nav.updates")):
            pill = Pill(b, self, key=key, kind="nav", surface=s, stretch=True, height=42, radius=14,
                        anchor="w", padx=34, size=10, bold=True, command=lambda p=page: self.show(p))
            pill.pack(fill="x", pady=3)
            self.nav[page], self.nav_keys[page] = pill, key

        # bottom block (packed bottom-up)
        Lbl(b, self, key="hotkeys", kind="muted", size=8, surface=s, wrap=200).pack(side="bottom", anchor="w",
                                                                                   padx=6, pady=(14, 4))
        th = Segmented(b, self, [("light", "", "theme.light"), ("dark", "", "theme.dark")],
                       self.cfg.theme, self.set_theme, surface=s)
        th.pack(side="bottom", anchor="w", pady=(8, 0))
        self.theme_segs.append(th)
        ul = Segmented(b, self, [("ru", "RU", None), ("en", "EN", None), ("uk", "UK", None)],
                       self.cfg.ui_language, self.set_ui_language, surface=s)
        ul.pack(side="bottom", anchor="w")
        self.ui_segs.append(ul)

    def _header(self, p, title_key, sub_key) -> None:
        Lbl(p, self, key=title_key, size=22, bold=True).pack(anchor="w")
        Lbl(p, self, key=sub_key, kind="muted", size=10, wrap=640).pack(anchor="w", pady=(2, 16))

    def _row(self, card, key, stack=False):
        s = card.surf
        r = Frm(card.body, self, s)
        r.pack(fill="x", pady=7)
        if stack:
            Lbl(r, self, key=key, kind="muted", size=9, surface=s).pack(anchor="w", pady=(0, 6))
            right = Frm(r, self, s)
            right.pack(anchor="w")
        else:
            right = Frm(r, self, s)
            right.pack(side="right")
            Lbl(r, self, key=key, size=10, surface=s, wrap=190).pack(side="left")
        return right

    # ---- pages
    def _build_home(self, p) -> None:
        self._header(p, "home.title", "home.subtitle")
        status = Card(p, self)
        status.pack(fill="x", pady=(0, 14))
        b, s = status.body, status.surf

        top = Frm(b, self, s)
        top.pack(fill="x")
        self.dot = Dot(top, self, s)
        self.dot.pack(side="left", padx=(0, 10))
        self.lbl_state = Lbl(top, self, text="", size=15, bold=True, surface=s)
        self.lbl_state.pack(side="left")
        self.lbl_match = Lbl(top, self, text="", kind="muted", size=10, surface=s)
        self.lbl_match.pack(side="right")

        tiles = Frm(b, self, s)
        tiles.pack(fill="x", pady=(16, 16))
        for i in range(3):
            tiles.columnconfigure(i, weight=1, uniform="tiles")
        self.vals: dict[str, Lbl] = {}
        for i, key in enumerate(("stat.games", "stat.cycles", "stat.time")):
            tile = Card(tiles, self, surface=s, fill="soft", radius=16, pad=14)
            tile.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 10, 0))
            Lbl(tile.body, self, key=key, kind="muted", size=9, surface="soft").pack(anchor="w")
            v = Lbl(tile.body, self, text="0", size=20, bold=True, surface="soft")
            v.pack(anchor="w")
            self.vals[key] = v

        row = Frm(b, self, s)
        row.pack(fill="x")
        Pill(row, self, key="btn.start", kind="primary", surface=s, minw=120, bold=True,
             command=self.engine.start).pack(side="left")
        self.btn_pause = Pill(row, self, key="btn.pause", kind="soft", surface=s, minw=100,
                              command=self.engine.toggle_pause)
        self.btn_pause.pack(side="left", padx=8)
        Pill(row, self, key="btn.stop", kind="soft", surface=s, minw=80, command=self.engine.stop).pack(side="left")
        Pill(row, self, key="btn.reset", kind="soft", surface=s, command=self.engine.reset_stats).pack(
            side="left", padx=8)

        logc = Card(p, self, fixed=True)
        logc.pack(fill="both", expand=True)
        Lbl(logc.body, self, key="log.title", size=11, bold=True, surface=logc.surf).pack(anchor="w", pady=(0, 8))
        self.logbox = tk.Text(logc.body, relief="flat", bd=0, highlightthickness=0, wrap="word",
                              state="disabled", padx=2, pady=2, height=4)
        self.logbox.pack(fill="both", expand=True)

    def _build_settings(self, p) -> None:
        self._header(p, "settings.title", "settings.subtitle")
        cols = Frm(p, self, "bg")
        cols.pack(fill="x")
        cols.columnconfigure((0, 1), weight=1, uniform="c")

        gen = Card(cols, self)
        gen.grid(row=0, column=0, sticky="new", padx=(0, 8))
        Lbl(gen.body, self, key="set.general", size=11, bold=True, surface=gen.surf).pack(anchor="w", pady=(0, 4))
        ul = Segmented(self._row(gen, "set.ui_language", stack=True), self,
                       [("ru", "RU", None), ("en", "EN", None), ("uk", "UK", None)],
                       self.cfg.ui_language, self.set_ui_language)
        ul.pack()
        self.ui_segs.append(ul)
        self.seg_game = Segmented(self._row(gen, "set.game_language", stack=True), self,
                                  [("ru", "RU", None), ("en", "EN", None)],
                                  self.cfg.language, self.set_game_language)
        self.seg_game.pack()
        th = Segmented(self._row(gen, "set.theme", stack=True), self,
                       [("light", "", "theme.light"), ("dark", "", "theme.dark")], self.cfg.theme, self.set_theme)
        th.pack()
        self.theme_segs.append(th)

        rec = Card(cols, self)
        rec.grid(row=0, column=1, sticky="new", padx=(8, 0))
        s = rec.surf
        Lbl(rec.body, self, key="set.recognition", size=11, bold=True, surface=s).pack(anchor="w", pady=(0, 4))
        self.v_thr = tk.DoubleVar(value=self.cfg.threshold)
        self.v_scan = tk.DoubleVar(value=self.cfg.scan_interval)
        self.v_delay = tk.DoubleVar(value=self.cfg.click_delay)
        self.v_fg = tk.BooleanVar(value=self.cfg.require_foreground)
        self.v_focus = tk.BooleanVar(value=self.cfg.auto_focus)

        r = self._row(rec, "set.threshold", stack=True)
        Slider(r, self, self.v_thr, 0.5, 0.99, surface=s).pack(side="left")
        self.lbl_thr = Lbl(r, self, text="", size=10, bold=True, surface=s)
        self.lbl_thr.pack(side="left", padx=(6, 0))
        self.v_thr.trace_add("write", lambda *a: self.lbl_thr.configure(text=f"{self.v_thr.get():.2f}"))
        self.lbl_thr.configure(text=f"{self.v_thr.get():.2f}")
        Stepper(self._row(rec, "set.scan"), self, self.v_scan, 0.2, 5.0, 0.1).pack()
        Stepper(self._row(rec, "set.delay"), self, self.v_delay, 0.5, 10.0, 0.5).pack()
        Toggle(self._row(rec, "set.foreground"), self, self.v_fg).pack()
        Toggle(self._row(rec, "set.focus"), self, self.v_focus).pack()

        Pill(p, self, key="btn.save", kind="primary", bold=True, surface="bg", minw=130,
             command=self.save_settings).pack(anchor="w", pady=(16, 0))

    def _build_afk(self, p) -> None:
        self._header(p, "afk.title", "afk.subtitle")
        card = Card(p, self)
        card.pack(fill="x")
        s = card.surf
        self.v_afk = tk.BooleanVar(value=self.cfg.afk_enabled)
        self.v_afk_int = tk.DoubleVar(value=self.cfg.afk_interval)
        self.v_afk_hold = tk.DoubleVar(value=self.cfg.afk_hold)
        Toggle(self._row(card, "afk.enabled"), self, self.v_afk).pack()
        Stepper(self._row(card, "afk.interval"), self, self.v_afk_int, 1, 120, 1, decimals=0).pack()
        Stepper(self._row(card, "afk.hold"), self, self.v_afk_hold, 0.5, 10, 0.5).pack()
        keys = self._row(card, "afk.keys")
        self.afk_chips: dict[str, Pill] = {}
        for k in "wasd":
            chip = Pill(keys, self, text=k.upper(), kind="chip", surface=s, height=32, minw=40, bold=True,
                        command=lambda k=k: self._toggle_key(k))
            chip.set_selected(k in self.cfg.afk_keys)
            chip.pack(side="left", padx=3)
            self.afk_chips[k] = chip
        Pill(p, self, key="btn.save", kind="primary", bold=True, surface="bg", minw=130,
             command=self.save_settings).pack(anchor="w", pady=(16, 0))

    def _toggle_key(self, k) -> None:
        chip = self.afk_chips[k]
        chip.set_selected(not chip.selected)

    def _build_templates(self, p) -> None:
        self._header(p, "tpl.title", "tpl.subtitle")
        card = Card(p, self)
        card.pack(fill="x")
        s = card.surf
        self.lst = tk.Listbox(card.body, height=7, relief="flat", bd=0, highlightthickness=0,
                              activestyle="none", exportselection=False)
        self.lst.pack(fill="x")
        bar = Frm(card.body, self, s)
        bar.pack(fill="x", pady=(14, 0))
        self.v_role = tk.StringVar(value="start")
        self.v_name = tk.StringVar(value="play")
        self.seg_role = Segmented(bar, self, [(r, r, None) for r in ROLES], "start",
                                  lambda v: self.v_role.set(v), surface=s)
        self.seg_role.pack(side="left")
        Field(bar, self, self.v_name, width=12, surface=s).pack(side="left", padx=8)
        Pill(bar, self, key="tpl.capture", kind="primary", surface=s, bold=True, command=self.capture).pack(side="left")
        Pill(bar, self, key="tpl.delete", kind="soft", surface=s, command=self.delete_template).pack(side="left", padx=8)
        Pill(bar, self, key="tpl.test", kind="soft", surface=s, command=self.test_now).pack(side="left")
        self.lbl_test = Lbl(p, self, text="", kind="muted", size=9, wrap=700)
        self.lbl_test.pack(anchor="w", pady=(12, 0))
        Lbl(p, self, key="tpl.legend", kind="muted", size=9, wrap=700).pack(anchor="w", pady=(8, 0))

    def _build_updates(self, p) -> None:
        self._header(p, "upd.title", "upd.subtitle")
        card = Card(p, self)
        card.pack(fill="x")
        s = card.surf
        self.lbl_ver = Lbl(card.body, self, key="upd.version", size=11, bold=True, surface=s)
        self.lbl_ver.fmt = {"v": updater.local_version(BASE)}
        self.lbl_ver.pack(anchor="w", pady=(0, 10))
        Lbl(card.body, self, key="upd.url", kind="muted", size=9, surface=s).pack(anchor="w", pady=(0, 6))
        self.v_url = tk.StringVar(value=self.cfg.update_url)
        Field(card.body, self, self.v_url, width=52, surface=s).pack(anchor="w")
        self.v_auto = tk.BooleanVar(value=self.cfg.auto_update)
        row = Frm(card.body, self, s)
        row.pack(fill="x", pady=(14, 4))
        Toggle(row, self, self.v_auto, surface=s).pack(side="left")
        Lbl(row, self, key="upd.auto", size=10, surface=s).pack(side="left", padx=10)
        bar = Frm(card.body, self, s)
        bar.pack(fill="x", pady=(12, 0))
        self.btn_upd = Pill(bar, self, key="upd.check", kind="primary", surface=s, bold=True, minw=190,
                            command=self._upd_clicked)
        self.btn_upd.pack(side="left")
        self.lbl_upd = Lbl(bar, self, text="", kind="muted", size=10, surface=s)
        self.lbl_upd.pack(side="left", padx=14)
        Lbl(p, self, key="upd.warn", kind="muted", size=9, wrap=700).pack(anchor="w", pady=(14, 0))

    def _set_upd_status(self, key: str | None, **kw) -> None:
        self.lbl_upd.key, self.lbl_upd.fmt = key, kw
        if key:
            self.lbl_upd.retext()
        else:
            self.lbl_upd.configure(text="")

    def _upd_clicked(self) -> None:
        if self.pending_update:
            self._start_install(self.pending_update, auto=False)
        else:
            self.check_updates(auto=False)

    def check_updates(self, auto: bool = False) -> None:
        self.cfg.update_url = self.v_url.get().strip()
        self.cfg.auto_update = bool(self.v_auto.get())
        self.cfg.save(CONFIG_PATH)
        if not self.cfg.update_url:
            self._set_upd_status("upd.need_url")
            return
        self._set_upd_status("upd.checking")

        def work(url=self.cfg.update_url):
            try:
                version, manifest = updater.check(BASE, url)
                self.upq.put(("available", manifest, auto) if manifest else ("latest", version, auto))
            except Exception as exc:  # network, JSON, https-only, ...
                self.upq.put(("error", str(exc), auto))

        threading.Thread(target=work, daemon=True).start()

    def _start_install(self, manifest: dict, auto: bool) -> None:
        self._set_upd_status("upd.installing")

        def work():
            try:
                self.upq.put(("done", updater.install(BASE, manifest), auto))
            except Exception as exc:
                self.upq.put(("error", str(exc), auto))

        threading.Thread(target=work, daemon=True).start()

    def _handle_update_event(self, ev: tuple) -> None:
        kind, payload, auto = ev
        if kind == "latest":
            self.pending_update = None
            self.btn_upd.set_key("upd.check")
            self._set_upd_status("upd.latest", v=payload)
        elif kind == "available":
            self.pending_update = payload
            self.btn_upd.set_key("upd.install")
            self._set_upd_status("upd.available", v=payload["version"])
            self._log("upd.available", v=payload["version"])
            if auto and not self.engine.running:
                self._start_install(payload, auto=True)
        elif kind == "error":
            self._set_upd_status("upd.failed", err=payload)
            self._log("upd.failed", err=payload)
        elif kind == "done":
            self.pending_update = None
            self.btn_upd.set_key("upd.check")
            self.lbl_ver.fmt = {"v": payload}
            self.lbl_ver.retext()
            if self.engine.running:
                self._set_upd_status("upd.done_running", v=payload)
                self._log("upd.done_running", v=payload)
            else:
                self._set_upd_status("upd.done", v=payload)
                self._log("upd.done", v=payload)
                self.restart_requested = True
                self.after(1200, self._close)

    # ---- navigation / switches
    def show(self, page: str) -> None:
        self.current = page
        self.pages[page].tkraise()
        for k, pill in self.nav.items():
            pill.set_selected(k == page)

    def set_ui_language(self, lang: str) -> None:
        self.cfg.ui_language = lang
        for seg in self.ui_segs:
            seg.set(lang)
        self.cfg.save(CONFIG_PATH)
        self.refresh_all()

    def set_theme(self, name: str) -> None:
        self.cfg.theme = name
        self.c = PALETTES[name]
        for seg in self.theme_segs:
            seg.set(name)
        self.cfg.save(CONFIG_PATH)
        self.refresh_all()

    def set_game_language(self, lang: str) -> None:
        self.cfg.language = lang
        self.cfg.save(CONFIG_PATH)
        if self.engine.running:
            self.engine.reload_templates()
        self.refresh_templates()

    # ---- actions
    def save_settings(self) -> None:
        cfg = self.cfg
        try:
            cfg.threshold = round(float(self.v_thr.get()), 2)
            cfg.scan_interval = float(self.v_scan.get())
            cfg.click_delay = float(self.v_delay.get())
            cfg.require_foreground = bool(self.v_fg.get())
            cfg.auto_focus = bool(self.v_focus.get())
            cfg.afk_enabled = bool(self.v_afk.get())
            cfg.afk_interval = float(self.v_afk_int.get())
            cfg.afk_hold = float(self.v_afk_hold.get())
            cfg.afk_keys = "".join(k for k, chip in self.afk_chips.items() if chip.selected)
        except (tk.TclError, ValueError):
            messagebox.showerror("Easy Rewards", self.tr("dlg.invalid"))
            return
        cfg.save(CONFIG_PATH)
        if self.engine.running:
            self.engine.reload_templates()
        self._log("log.saved")

    def refresh_templates(self) -> None:
        self.lst.delete(0, "end")
        self._tpl_names = []
        for t in load_templates(TEMPLATES, self.cfg.language):
            h, w = t.gray.shape[:2]
            self.lst.insert("end", f"  {t.name}     [{t.role}]     {w}×{h}px")
            self._tpl_names.append(t.name)
        if not self._tpl_names:
            self.lst.insert("end", "  " + self.tr("tpl.none", lang=self.cfg.language))

    def capture(self) -> None:
        name = "".join(ch for ch in self.v_name.get() if ch.isalnum() or ch == "-") or "button"
        path = TEMPLATES / self.cfg.language / f"{self.v_role.get()}_{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        messagebox.showinfo(self.tr("dlg.capture_title"), self.tr("dlg.capture_text"))
        self.withdraw()
        self.update()
        time.sleep(5)
        frame = self.io.grab()
        win = "Easy Rewards - ENTER / C"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, 1280, 720)
        x, y, w, h = cv2.selectROI(win, frame, showCrosshair=False)
        cv2.destroyAllWindows()
        self.deiconify()
        if w < 8 or h < 8:
            self._log("log.capture_cancelled")
            return
        ok, buf = cv2.imencode(".png", frame[y:y + h, x:x + w])
        if ok:
            buf.tofile(str(path))
            self._log("log.capture_saved", name=path.name, w=w, h=h)
        self.refresh_templates()

    def delete_template(self) -> None:
        sel = self.lst.curselection()
        if not sel or sel[0] >= len(self._tpl_names):
            return
        p = TEMPLATES / self.cfg.language / f"{self._tpl_names[sel[0]]}.png"
        if p.exists() and messagebox.askyesno(self.tr("dlg.delete_title"), self.tr("dlg.delete_text", name=p.name)):
            p.unlink()
            self.refresh_templates()

    def test_now(self) -> None:
        tpls = load_templates(TEMPLATES, self.cfg.language)
        if not tpls:
            self.lbl_test.configure(text=self.tr("tpl.none", lang=self.cfg.language))
            return
        gray = cv2.cvtColor(self.io.grab(), cv2.COLOR_BGR2GRAY)
        scores = "   ".join(f"{t.name}: {best_match(gray, t.gray, self.cfg.scales)[0]:.2f}" for t in tpls)
        self.lbl_test.configure(text=self.tr("tpl.scores", thr=f"{self.cfg.threshold:.2f}") + "  " + scores)

    # ---- periodic refresh
    def _log(self, key: str, **kw) -> None:
        self.logq.put((time.strftime("%H:%M:%S"), key, kw))

    def _tick(self) -> None:
        e = self.engine
        self.lbl_state.configure(text=self.tr("state." + e.state))
        self.lbl_match.configure(text=f"{self.tr('stat.match')}  {e.score:.2f}")
        self.vals["stat.games"].configure(text=str(e.games))
        self.vals["stat.cycles"].configure(text=str(e.cycles))
        sec = int(e.runtime)
        self.vals["stat.time"].configure(text=f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}")
        self.dot.set_color("warn" if e.paused else "ok" if e.running else "off")
        self.btn_pause.set_key("btn.resume" if e.paused else "btn.pause")

        while True:
            try:
                self._handle_update_event(self.upq.get_nowait())
            except queue.Empty:
                break

        items = []
        while True:
            try:
                items.append(self.logq.get_nowait())
            except queue.Empty:
                break
        if items:
            self.logbox.configure(state="normal")
            for ts, key, kw in items:
                self.logbox.insert("end", ts + "  ", "ts")
                self.logbox.insert("end", self.tr(key, **kw) + "\n")
            lines = int(self.logbox.index("end-1c").split(".")[0])
            if lines > 500:
                self.logbox.delete("1.0", f"{lines - 500}.0")
            self.logbox.see("end")
            self.logbox.configure(state="disabled")
        self.after(250, self._tick)

    def report_callback_exception(self, exc_type, exc, tb) -> None:
        write_crash(exc_type, exc, tb)
        self._log("log.error", err=f"{exc_type.__name__}: {exc}")

    def _close(self) -> None:
        self.engine.stop()
        self.cfg.save(CONFIG_PATH)
        self.destroy()


# ------------------------------------------------------------------ CLI
def run_cli() -> None:
    cfg = Config.load(CONFIG_PATH)
    engine = Engine(cfg, WinIO(), TEMPLATES,
                    log=lambda key, **kw: print(tr(cfg.ui_language, key, **kw)))
    HotkeyPoller({"F7": engine.start, "F8": engine.stop, "F10": engine.toggle_pause}).start()
    print(tr(cfg.ui_language, "hotkeys"))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        engine.stop()


def main() -> int:
    if sys.platform != "win32":
        print("Easy Rewards only runs on Windows.")
        return 1
    try:
        if "--cli" in sys.argv:
            run_cli()
            return 0
        app = App()
        app.mainloop()
    except Exception:
        print(write_crash(*sys.exc_info()))
        return 1
    if app.restart_requested:
        if os.environ.get("EASY_REWARDS_LAUNCHER"):
            return 42  # run.bat starts us again
        subprocess.Popen([sys.executable] + sys.argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
