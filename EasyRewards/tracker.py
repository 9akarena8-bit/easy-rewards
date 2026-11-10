"""Manual-farming tracker: counters with goals, token count, prize checklist, season week, luck maths.

Data lives in tracker.json (never touched by updates). Everything here is plain Python and thread safe.
"""
from __future__ import annotations

import copy
import json
import math
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

DEFAULTS = {
    "counters": [
        {"id": "chests", "key": "trk.c_chests", "name": "", "value": 0, "goals": [25, 100, 250, 500, 1000]},
        {"id": "rare", "key": "trk.c_rare", "name": "", "value": 0, "goals": [2, 10, 25, 50, 100]},
        {"id": "sprite", "key": "trk.c_sprite", "name": "", "value": 0, "goals": [1, 5, 10, 25, 50]},
    ],
    "tokens": 0,
    "prizes": [],
    "week_start": "",      # local time, "YYYY-MM-DDTHH:MM"; empty = no season timer
    "odds": 137500,        # base chance of a token is 1 in `odds` per chest
    "boost": 1.0,          # drop boost multiplier (1, 1.5, 2)
    "rev": 0,              # increments on every change so the UI knows when to redraw
}


def _int(v, lo=0, hi=10_000_000, default=0) -> int:
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        return default


def _goals(v) -> list[int]:
    if isinstance(v, str):
        v = [x for x in v.replace(";", ",").split(",")]
    out = []
    for x in v or []:
        n = _int(x, 1, 10_000_000, 0)
        if n:
            out.append(n)
    return sorted(set(out))[:8]


def _week_ok(v: str) -> str:
    if not v:
        return ""
    try:
        datetime.fromisoformat(v)
        return v
    except ValueError:
        return ""


def normalise(raw: dict) -> dict:
    """Turn any (possibly imported) dict into a valid tracker document."""
    d = copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        return d
    counters = []
    for c in raw.get("counters", []) if isinstance(raw.get("counters"), list) else []:
        if not isinstance(c, dict):
            continue
        counters.append({"id": str(c.get("id") or uuid.uuid4().hex[:8])[:24],
                         "key": str(c.get("key") or "")[:40],
                         "name": str(c.get("name") or "")[:40],
                         "value": _int(c.get("value")),
                         "goals": _goals(c.get("goals"))})
    if "counters" in raw:
        d["counters"] = counters[:24]
    d["tokens"] = _int(raw.get("tokens"))
    prizes = []
    for p in raw.get("prizes", []) if isinstance(raw.get("prizes"), list) else []:
        if isinstance(p, dict) and str(p.get("name", "")).strip():
            prizes.append({"id": str(p.get("id") or uuid.uuid4().hex[:8])[:24],
                           "name": str(p["name"]).strip()[:60], "found": bool(p.get("found"))})
    d["prizes"] = prizes[:200]
    d["week_start"] = _week_ok(str(raw.get("week_start", "")))
    d["odds"] = _int(raw.get("odds", DEFAULTS["odds"]), 1, 100_000_000, DEFAULTS["odds"])
    try:
        d["boost"] = max(1.0, min(10.0, float(raw.get("boost", 1.0))))
    except (TypeError, ValueError):
        d["boost"] = 1.0
    d["rev"] = _int(raw.get("rev"))
    return d


class Tracker:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data = self._load()

    # ---- persistence
    def _load(self) -> dict:
        try:
            return normalise(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return normalise({})
        except (OSError, ValueError):
            try:
                self.path.replace(self.path.with_suffix(".bad"))
            except OSError:
                pass
            return normalise({})

    def _save(self) -> None:
        self.data["rev"] += 1
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def snapshot(self) -> dict:
        with self.lock:
            return copy.deepcopy(self.data)

    # ---- counters
    def _counter(self, cid: str) -> dict:
        for c in self.data["counters"]:
            if c["id"] == cid:
                return c
        raise KeyError(cid)

    def counter_add(self, cid: str, delta: int) -> int:
        with self.lock:
            c = self._counter(cid)
            c["value"] = _int(c["value"] + int(delta))
            self._save()
            return c["value"]

    def counter_set(self, cid: str, value) -> int:
        with self.lock:
            c = self._counter(cid)
            c["value"] = _int(value)
            self._save()
            return c["value"]

    def counter_edit(self, cid: str, name: str | None = None, goals=None) -> None:
        with self.lock:
            c = self._counter(cid)
            if name is not None:
                c["name"] = str(name).strip()[:40]
            if goals is not None:
                c["goals"] = _goals(goals)
            self._save()

    def counter_new(self, name: str, goals=None) -> str:
        with self.lock:
            if len(self.data["counters"]) >= 24:
                raise ValueError("too many counters")
            cid = uuid.uuid4().hex[:8]
            self.data["counters"].append({"id": cid, "key": "", "name": str(name).strip()[:40] or "Counter",
                                          "value": 0, "goals": _goals(goals)})
            self._save()
            return cid

    def counter_delete(self, cid: str) -> None:
        with self.lock:
            self.data["counters"] = [c for c in self.data["counters"] if c["id"] != cid]
            self._save()

    def tokens_add(self, delta: int) -> int:
        with self.lock:
            self.data["tokens"] = _int(self.data["tokens"] + int(delta))
            self._save()
            return self.data["tokens"]

    # ---- prizes
    def prize_add(self, name: str) -> str:
        name = str(name).strip()[:60]
        if not name:
            raise ValueError("empty name")
        with self.lock:
            pid = uuid.uuid4().hex[:8]
            self.data["prizes"].append({"id": pid, "name": name, "found": False})
            self._save()
            return pid

    def prize_toggle(self, pid: str) -> None:
        with self.lock:
            for p in self.data["prizes"]:
                if p["id"] == pid:
                    p["found"] = not p["found"]
            self._save()

    def prize_delete(self, pid: str) -> None:
        with self.lock:
            self.data["prizes"] = [p for p in self.data["prizes"] if p["id"] != pid]
            self._save()

    # ---- options / backup
    def set_options(self, patch: dict) -> None:
        with self.lock:
            if "odds" in patch:
                self.data["odds"] = _int(patch["odds"], 1, 100_000_000, self.data["odds"])
            if "boost" in patch:
                try:
                    self.data["boost"] = max(1.0, min(10.0, float(patch["boost"])))
                except (TypeError, ValueError):
                    pass
            if "week_start" in patch:
                self.data["week_start"] = _week_ok(str(patch["week_start"]))
            self._save()

    def export_to(self, path) -> None:
        with self.lock:
            Path(path).write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    def import_from(self, path) -> None:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "counters" not in raw:
            raise ValueError("not a tracker file")
        with self.lock:
            rev = self.data["rev"]
            self.data = normalise(raw)
            self.data["rev"] = rev
            self._save()

    def reset(self) -> None:
        with self.lock:
            rev = self.data["rev"]
            self.data = normalise({})
            self.data["rev"] = rev
            self._save()

    # ---- derived numbers
    def luck(self) -> dict:
        """Chance maths for 'at least one token in n chests' with the current odds and boost."""
        with self.lock:
            d = self.data
            chests = d["counters"][0]["value"] if d["counters"] else 0
            return luck(chests, d["odds"], d["boost"])

    def week_info(self, now: datetime | None = None) -> dict | None:
        with self.lock:
            ws = self.data["week_start"]
        if not ws:
            return None
        now = now or datetime.now()
        start = datetime.fromisoformat(ws)
        if now < start:
            return None
        n = (now - start).days // 7 + 1
        left = start + timedelta(days=7 * n) - now
        return {"n": n, "d": left.days, "h": left.seconds // 3600}


def luck(chests: int, odds: int, boost: float) -> dict:
    odds = max(1, int(odds))
    p = min(1.0, max(0.0, boost / odds))
    if p >= 1.0:
        n50 = n90 = 1
    else:
        n50 = math.ceil(math.log(0.5) / math.log1p(-p))
        n90 = math.ceil(math.log(0.1) / math.log1p(-p))
    return {"chests": chests, "one_in": round(odds / boost) if boost else odds, "p": p,
            "chance": 1 - (1 - p) ** chests, "n50": n50, "n90": n90}
