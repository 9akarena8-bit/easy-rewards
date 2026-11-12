"""Standalone desktop/web checkout demo order ledger, never a payment processor.

Future card/SBP provider callbacks, merchant bank reconciliation, and Steam trade
confirmation must be implemented by a trusted merchant service before any order
can grant a licence. Client-controlled draft data is never financial proof.
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

PLAN_DAYS = {"day": 1, "three_days": 3, "week": 7, "month": 30}
METHODS = {"card", "sbp", "qr", "bank_transfer", "steam_items"}
GAMES = {"dota2", "rust", "cs2", "tf2", "pubg", "dst", "naraka"}
ORDER_ID = re.compile(r"^[A-F0-9]{16}$")
USER_REF = re.compile(r"^[A-Za-z0-9_-]{6,64}$")

@dataclass(frozen=True)
class Draft:
    order_id: str
    plan: str
    method: str
    created_at: int
    status: str
    game: str = ""


class DemoOrderLedger:
    """Non-payable merchant-side ledger with deliberately non-creditable orders."""

    def __init__(self, database_path: Path):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS demo_orders(
                id TEXT PRIMARY KEY, plan TEXT NOT NULL, method TEXT NOT NULL,
                game TEXT NOT NULL, created_at INTEGER NOT NULL,
                status TEXT NOT NULL, basket_json TEXT NOT NULL,
                customer_ref TEXT NOT NULL DEFAULT '', review_note TEXT NOT NULL DEFAULT ''
            )""")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def create(self, *, plan: str, method: str, game: str = "", basket=None,
               customer_ref: str = "") -> dict:
        if plan not in PLAN_DAYS or method not in METHODS:
            raise ValueError("Unknown plan or payment method")
        if not isinstance(customer_ref, str) or (customer_ref and not USER_REF.fullmatch(customer_ref)):
            raise ValueError("Invalid customer reference")
        if (method == "steam_items" and game not in GAMES) or (method != "steam_items" and game):
            raise ValueError("Game is required only for skin checkout")
        if basket is None:
            basket = []
        if not isinstance(basket, list) or len(basket) > 16:
            raise ValueError("Invalid item list")
        if method != "steam_items" and basket:
            raise ValueError("Only skin checkout can include item estimates")
        safe_items = []
        for item in basket:
            if not isinstance(item, dict):
                raise ValueError("Malformed basket entry")
            name, estimate = item.get("name"), item.get("estimate_kopeks")
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                raise ValueError("Invalid item name")
            if type(estimate) is not int or not 1 <= estimate <= 100_000_000:
                raise ValueError("Invalid *unverified* value")
            safe_items.append({"name": name.strip(), "estimate_kopeks": estimate, "verified": False})
        now = int(time.time())
        order_id = secrets.token_hex(8).upper()
        with self.lock, self._connect() as db:
            db.execute("INSERT INTO demo_orders VALUES(?,?,?,?,?,?,?,?,?)",
                       (order_id, plan, method, game, now, "demo_created",
                        json.dumps(safe_items, ensure_ascii=False), customer_ref, ""))
            db.commit()
        return self.status(order_id)

    def status(self, order_id: str) -> dict:
        if not isinstance(order_id, str) or not ORDER_ID.fullmatch(order_id):
            raise ValueError("Invalid order ID")
        with self.lock, self._connect() as db:
            row = db.execute("SELECT * FROM demo_orders WHERE id=?", (order_id,)).fetchone()
            if row is None:
                raise LookupError("Demo order not found")
            return {
                "order_id": row["id"], "plan": row["plan"],
                "days": PLAN_DAYS[row["plan"]], "method": row["method"],
                "game": row["game"], "status": row["status"],
                "created_at": row["created_at"],
                "customer_ref": row["customer_ref"],
                "basket": json.loads(row["basket_json"]),
                "review_note": row["review_note"],
                "demo": True, "payment_verified": False,
                "licence_granted": False, "payment_url": None,
                "trade_offer_url": None, "real_prices": False,
                "reversible_days": 7 if row["game"] == "cs2" else 0,
            }

    def review(self, order_id: str, note: str) -> dict:
        """Only classifies an example draft; cannot mark a real payment paid."""
        if not isinstance(note, str) or not 1 <= len(note.strip()) <= 300:
            raise ValueError("Review note required")
        self.status(order_id)  # validate input before mutation
        with self.lock, self._connect() as db:
            db.execute("UPDATE demo_orders SET status='demo_reviewed', review_note=? WHERE id=?",
                       (note.strip(), order_id))
            db.commit()
        return self.status(order_id)

    def recent(self, limit: int = 20) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Limit must be 1..100")
        with self.lock, self._connect() as db:
            ids = [r["id"] for r in db.execute(
                "SELECT id FROM demo_orders ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))]
        return [self.status(x) for x in ids]