"""Minimal stand-in for tkinter so the GUI code can be smoke-tested without a display/Tk install."""
import sys
import types


class TclError(Exception):
    pass


class _Var:
    def __init__(self, master=None, value=None):
        self._v, self._cbs = value, []

    def get(self):
        return self._v

    def set(self, v):
        self._v = v
        for cb in list(self._cbs):
            cb()

    def trace_add(self, mode, cb):
        self._cbs.append(lambda: cb("n", "", "w"))


class StringVar(_Var):
    def __init__(self, master=None, value=""):
        super().__init__(master, value)


class BooleanVar(_Var):
    def __init__(self, master=None, value=False):
        super().__init__(master, value)


class DoubleVar(_Var):
    def __init__(self, master=None, value=0.0):
        super().__init__(master, value)


class Widget:
    registry = []

    def __init__(self, *a, **k):
        self._opts = dict(k)
        Widget.registry.append(self)

    def cget(self, k):
        return str(self._opts.get(k, 40))

    def configure(self, **k):
        self._opts.update(k)

    config = configure

    def winfo_width(self): return 400
    def winfo_height(self): return 300
    def winfo_reqheight(self): return 120
    def winfo_fpixels(self, s): return 96.0
    def index(self, *a): return "3.0"
    def curselection(self): return ()
    def after(self, *a, **k): return 0
    def mainloop(self): pass
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: 0


class Tk(Widget):
    pass


def install():
    tk = types.ModuleType("tkinter")
    for n in ("Frame", "Label", "Canvas", "Entry", "Text", "Listbox", "PhotoImage"):
        setattr(tk, n, type(n, (Widget,), {}))
    tk.Tk, tk.TclError = Tk, TclError
    tk.StringVar, tk.BooleanVar, tk.DoubleVar = StringVar, BooleanVar, DoubleVar
    font = types.ModuleType("tkinter.font")
    font.Font = type("Font", (), {"__init__": lambda self, **k: None,
                                  "measure": lambda self, t: 7 * len(t)})
    mb = types.ModuleType("tkinter.messagebox")
    mb.showinfo = mb.showerror = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: True
    tk.font, tk.messagebox = font, mb
    sys.modules.update({"tkinter": tk, "tkinter.font": font, "tkinter.messagebox": mb})
