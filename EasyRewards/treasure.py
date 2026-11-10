"""Treasure Hours: schedule, countdown and live Pirate Shop Access odds.
Stdlib-only, UI-independent. Custom events: treasure.json next to config.json ->
{"events": [{"start": "2026-12-05T22:00", "end": "2026-12-06T00:00",
             "mult": {"pirate_token": 1.5}, "note": "weekend"}]}
Naive datetimes are treated as GMT+3 (Epic's publish timezone)."""
from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

GMT3 = timezone(timedelta(hours=3), "GMT+3")

BASE_ODDS = {
    "gold_outfit": 1_562_500, "pirate_token": 137_500, "vehicle_decal": 7_813,
    "pickaxe_backbling": 568, "jam_track": 391, "loading_screen": 272, "gizmo_any": 127,
}

def _dt(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    return d.replace(tzinfo=GMT3) if d.tzinfo is None else d.astimezone(GMT3)

@dataclass
class Event:
    start: datetime
    end: datetime
    mult: dict
    note: str = ""
    def status(self, now: datetime) -> str:
        return "upcoming" if now < self.start else ("active" if now < self.end else "ended")

_BUILTIN = [
    Event(_dt("2026-11-07T22:00"), _dt("2026-11-08T00:00"), {"gold_outfit": 7.5, "pirate_token": 1.5, "vehicle_decal": 10}),
    Event(_dt("2026-11-08T05:00"), _dt("2026-11-08T07:00"), {"gold_outfit": 10, "pirate_token": 2.0, "vehicle_decal": 10}),
    Event(_dt("2026-11-14T22:00"), _dt("2026-11-15T00:00"), {"gold_outfit": 7.5, "pirate_token": 1.5, "vehicle_decal": 10}, "weekend"),
    Event(_dt("2026-11-28T22:00"), _dt("2026-11-29T00:00"), {"gold_outfit": 7.5, "pirate_token": 1.5, "vehicle_decal": 10}),
    Event(_dt("2026-11-29T05:00"), _dt("2026-11-29T07:00"), {"gold_outfit": 7.5, "pirate_token": 1.5, "vehicle_decal": 10}),
]

_CACHE: dict = {}

def load_events(path: Optional[Path] = None) -> list[Event]:
    p = Path(path) if path else None
    mtime = p.stat().st_mtime if p and p.is_file() else None
    hit = _CACHE.get((str(p), mtime))
    if hit is not None:
        return hit
    events = list(_BUILTIN)
    if p and p.is_file():
        try:
            for e in json.loads(p.read_text(encoding="utf-8")).get("events", []):
                events.append(Event(_dt(e["start"]), _dt(e["end"]), dict(e.get("mult", {})), str(e.get("note", ""))))
        except (OSError, ValueError, KeyError):
            pass
    events.sort(key=lambda x: x.start)
    _CACHE.clear()
    _CACHE[(str(p), mtime)] = events
    return events

def _ev_dict(e: Event, now: datetime) -> dict:
    return {"start": e.start.isoformat(), "end": e.end.isoformat(),
            "mult": e.mult, "note": e.note, "status": e.status(now)}

def countdown(e: Event, now: datetime) -> dict:
    t = max(0, int((e.start - now).total_seconds()))
    return {"total_s": t, "d": t // 86400, "h": t // 3600 % 24, "m": t // 60 % 60, "s": t % 60,
            "text": f"{t // 86400}:{t // 3600 % 24:02d}:{t // 60 % 60:02d}:{t % 60:02d}"}

def treasure_state(path: Optional[Path] = None, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(GMT3)
    events = load_events(path)
    active = next((e for e in events if e.status(now) == "active"), None)
    nxt = next((e for e in events if e.status(now) == "upcoming"), None)
    mult = active.mult if active else {}
    odds = {k: {"base": b, "mult": float(mult.get(k, 1.0)), "odds": round(b / float(mult.get(k, 1.0)))}
            for k, b in BASE_ODDS.items()}
    return {"active": active is not None,
            "event": _ev_dict(active, now) if active else None,
            "next": {**_ev_dict(nxt, now), "countdown": countdown(nxt, now)} if nxt else None,
            "odds": odds, "pirate_mult": odds["pirate_token"]["mult"],
            "pirate_odds": odds["pirate_token"]["odds"]}
