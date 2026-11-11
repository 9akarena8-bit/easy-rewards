"""Safe, offline checkout preparation for Fortnite Pirate Token.

NOT A PAYMENT PROCESSOR. A user-controlled desktop app cannot prove a payment
or Steam trade, activate a paid licence, or quote real-time market prices.
All completed payments and licence grants MUST be confirmed on an independent
merchant server before enabling this checkout.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

PLAN_IDS = frozenset({"day", "three_days", "week"})
METHODS = (
    {"id": "stars", "channel": "telegram", "kind": "digital", "ready": False,
     "requires": "Telegram Bot API successful_payment (XTR) verification on merchant server"},
    {"id": "card", "channel": "desktop_web", "kind": "fiat", "ready": False,
     "requires": "Merchant account, hosted checkout, verified payment.succeeded"},
    {"id": "sbp", "channel": "desktop_web", "kind": "fiat", "ready": False,
     "requires": "Merchant SBP checkout, verified payment.succeeded"},
    {"id": "qr", "channel": "desktop_web", "kind": "fiat", "ready": False,
     "requires": "Dynamic QR created by merchant PSP for an existing invoice"},
    {"id": "bank_transfer", "channel": "desktop_web", "kind": "fiat", "ready": False,
     "requires": "Merchant bank details and verified incoming transfer; manual review"},
    {"id": "steam_items", "channel": "desktop_web", "kind": "items", "ready": False,
     "requires": "Trusted inventory quotes, recipient verification, confirmed Steam trade"},
)
# Steam Community Market listing does NOT guarantee item tradability.
# The per-item tradable flag and applicable trade holds must be verified.
GAMES = (
    {"id": "dota2", "name": "Dota 2", "appid": 570, "trade_protected": False},
    {"id": "rust", "name": "Rust", "appid": 252490, "trade_protected": False},
    {"id": "tf2", "name": "Team Fortress 2", "appid": 440, "trade_protected": False},
    {"id": "pubg", "name": "PUBG: BATTLEGROUNDS", "appid": 578080, "trade_protected": False},
    {"id": "dst", "name": "Don't Starve Together", "appid": 322330, "trade_protected": False},
    {"id": "naraka", "name": "NARAKA: BLADEPOINT", "appid": 1203220, "trade_protected": False},
    {"id": "cs2", "name": "Counter-Strike 2", "appid": 730, "trade_protected": True,
     "reversal_days": 7},
)
METHOD_BY_ID = {m["id"]: m for m in METHODS}
GAME_BY_ID = {g["id"]: g for g in GAMES}


def catalog() -> dict:
    return {
        "active": False,
        "checkout_ready": False,
        "prices_configured": False,
        "real_market_quotes": False,
        "automatic_activation": False,
        "methods": [dict(m) for m in METHODS],
        "games": [dict(g) for g in GAMES],
        "message": "Checkout is not active. Do not send money or Steam items.",
    }


def pick_items(target_kopeks: int, verified_inventory: list[dict]) -> dict | None:
    """Find an exact or minimally overpaying *illustrative* combination.

    IMPORTANT: Call only on the future merchant backend with server-verified,
    recent, net RUB quotes. Never pass customer-supplied prices or use the
    result as proof of a trade. This function DOES NOT authorize any transfer.
    At most 16 items so exhaustive subset search is bounded.
    """
    if type(target_kopeks) is not int or target_kopeks <= 0:
        raise ValueError("invalid target")
    if not isinstance(verified_inventory, list) or len(verified_inventory) > 16:
        raise ValueError("inventory must contain <= 16 server-verified items")
    items = []
    ids = set()
    for obj in verified_inventory:
        if not isinstance(obj, dict):
            raise ValueError("invalid item")
        appid, amount, item_id = obj.get("appid"), obj.get("net_kopeks"), obj.get("assetid")
        if type(appid) is not int or type(amount) is not int or type(item_id) is not str:
            raise ValueError("missing verified quote")
        if not item_id or len(item_id) > 64 or item_id in ids or amount <= 0:
            raise ValueError("invalid item ID or price")
        if not obj.get("tradable") is True:
            continue
        if appid not in {g["appid"] for g in GAMES}:
            continue
        ids.add(item_id)
        items.append(obj)
    best = None
    for mask in range(1, 1 << len(items)):
        subset = [v for i, v in enumerate(items) if mask & (1 << i)]
        # Steam cannot mix CS2 protected items with unprotected items in one trade.
        cs2 = any(v["appid"] == 730 for v in subset)
        if cs2 and any(v["appid"] != 730 for v in subset):
            continue
        total = sum(v["net_kopeks"] for v in subset)
        if total < target_kopeks:
            continue
        key = (total - target_kopeks, len(subset), sorted(v["assetid"] for v in subset))
        if best is None or key < best[0]:
            best = (key, subset, total)
    if best is None:
        return None
    _, subset, total = best
    return {"target_kopeks": target_kopeks, "total_kopeks": total,
            "overpay_kopeks": total - target_kopeks,
            "assetids": [v["assetid"] for v in subset],
            "trade_protection_days": 7 if any(v["appid"] == 730 for v in subset) else 0,
            "authorized_to_deliver": False}


class LocalInterestDrafts:
    """Non-payable enquiries saved on the customer's PC, NOT merchant orders."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [d for d in data[-30:] if isinstance(d, dict)]
        except (OSError, ValueError):
            pass
        return []

    def recent(self) -> list[dict]:
        # This list is user-controlled. Always treat it as unverified.
        return [{"id": str(d.get("id", ""))[:16],
                 "plan": str(d.get("plan", ""))[:30],
                 "method": str(d.get("method", ""))[:30],
                 "game": str(d.get("game", ""))[:30],
                 "created_at": str(d.get("created_at", ""))[:45],
                 "status": "draft_only"} for d in self._read()[-8:][::-1]]

    def create(self, plan: str, method: str, game: str = "",
               skin_selection: dict | None = None) -> dict:
        if plan not in PLAN_IDS or method not in METHOD_BY_ID:
            return {"ok": False, "error": "invalid_plan_or_method"}
        if method == "steam_items":
            if game not in GAME_BY_ID:
                return {"ok": False, "error": "invalid_game"}
        elif game:
            return {"ok": False, "error": "unexpected_game"}
        # A user-entered skin basket is only a private planning note.
        # It is NOT a real inventory quote, Steam trade or verified price.
        basket = None
        if skin_selection is not None:
            if method != "steam_items" or not isinstance(skin_selection, dict):
                return {"ok": False, "error": "invalid_skin_selection"}
            raw = skin_selection.get("items")
            target = skin_selection.get("target_kopeks")
            if not isinstance(raw, list) or len(raw) > 16 or type(target) not in (int, type(None)):
                return {"ok": False, "error": "invalid_skin_selection"}
            if target is not None and not 1 <= target <= 100000000:
                return {"ok": False, "error": "invalid_skin_selection"}
            safe_items = []
            for item in raw:
                if not isinstance(item, dict):
                    return {"ok": False, "error": "invalid_skin_selection"}
                title, estimate = item.get("name"), item.get("estimate_kopeks")
                if (not isinstance(title, str) or not 1 <= len(title.strip()) <= 100
                        or type(estimate) is not int or not 1 <= estimate <= 100000000):
                    return {"ok": False, "error": "invalid_skin_selection"}
                safe_items.append({"name": title.strip(), "estimate_kopeks": estimate})
            basket = {"game": game, "items": safe_items,
                      "target_kopeks": target,
                      "verified": False, "market_quote": False}
        record = {"id": secrets.token_hex(6),
                  "plan": plan, "method": method, "game": game,
                  "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "status": "draft_only"}
        if basket is not None:
            record["skin_basket"] = basket
        current = self._read()
        current.append(record)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write prevents corrupt drafts on unexpected shutdown.
            temporary = self.path.with_name(self.path.name + ".tmp")
            temporary.write_text(json.dumps(current[-30:], indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            return {"ok": False, "error": "cannot_save_draft"}
        result = dict(record)
        result["ok"] = True
        result["disclaimer"] = "NOT an invoice. No payment details. Do not transfer money/items."
        result["payment_verified"] = False
        result["access_activated"] = False
        return result
