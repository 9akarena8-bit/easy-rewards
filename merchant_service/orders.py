"""SQLite storage for the private subscription demo."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import secrets
import sqlite3
import time

from subscription_preview import PLANS

CATALOG = {plan["id"]: plan for plan in PLANS if plan["hours"]}
METHODS = ("bank_transfer", "steam_items")
PENDING = ("awaiting_payment", "under_review")
REFERENCE = re.compile(r"DEMO-[A-Z0-9-]{4,64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{8,80}")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Orders:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction(write=True) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, role TEXT NOT NULL, credential TEXT UNIQUE NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts,
                    csrf TEXT NOT NULL, expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES accounts,
                    request_id TEXT NOT NULL, plan TEXT NOT NULL, days INTEGER NOT NULL,
                    amount_kopeks INTEGER NOT NULL, currency TEXT NOT NULL,
                    method TEXT NOT NULL, status TEXT NOT NULL, created_at INTEGER NOT NULL,
                    reference TEXT UNIQUE, confirmed_at INTEGER,
                    UNIQUE(account_id, request_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders,
                    actor TEXT NOT NULL REFERENCES accounts, action TEXT NOT NULL,
                    reason TEXT NOT NULL, occurred_at INTEGER NOT NULL,
                    UNIQUE(order_id, action)
                );
                CREATE TABLE IF NOT EXISTS friend_access (
                    account_id TEXT PRIMARY KEY REFERENCES accounts, expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS entitlements (
                    account_id TEXT PRIMARY KEY REFERENCES accounts, expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS referral_codes (
                    account_id TEXT PRIMARY KEY REFERENCES accounts, code TEXT UNIQUE NOT NULL
                );
                CREATE TABLE IF NOT EXISTS referrals (
                    invited_id TEXT PRIMARY KEY REFERENCES accounts,
                    inviter_id TEXT NOT NULL REFERENCES accounts,
                    qualified_order TEXT UNIQUE REFERENCES orders,
                    CHECK(invited_id != inviter_id)
                );
                CREATE TABLE IF NOT EXISTS referral_rewards (
                    source_order TEXT NOT NULL REFERENCES orders,
                    account_id TEXT NOT NULL REFERENCES accounts,
                    consumed_order TEXT UNIQUE REFERENCES orders,
                    PRIMARY KEY(source_order, account_id)
                );
            """)

    @contextmanager
    def transaction(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            with db:
                yield db
        finally:
            db.close()

    def provision(self, account_id, role):
        if not IDENTIFIER.fullmatch(account_id) or role not in ("buyer", "owner"):
            raise ValueError("invalid_account")
        credential = secrets.token_urlsafe(32)
        with self.transaction(write=True) as db:
            db.execute("INSERT INTO accounts VALUES(?,?,?)", (account_id, role, digest(credential)))
        return credential

    def login(self, credential, role):
        now = int(time.time())
        with self.transaction(write=True) as db:
            account = db.execute(
                "SELECT id FROM accounts WHERE credential=? AND role=?",
                (digest(credential), role),
            ).fetchone()
            if account is None:
                raise PermissionError("invalid_credentials")
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            db.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)",
                       (digest(token), account["id"], csrf, now + 3600))
        return token

    def actor(self, token, role):
        with self.transaction() as db:
            row = db.execute(
                """SELECT a.id, s.csrf FROM sessions s JOIN accounts a ON a.id=s.account_id
                   WHERE s.token=? AND a.role=? AND s.expires_at>?""",
                (digest(token), role, int(time.time())),
            ).fetchone()
        if row is None:
            raise PermissionError("authentication_required")
        return row

    def logout(self, token):
        with self.transaction(write=True) as db:
            db.execute("DELETE FROM sessions WHERE token=?", (digest(token),))

    @staticmethod
    def _order(db, order_id, account_id=None):
        row = db.execute(
            "SELECT * FROM orders WHERE order_id=? AND (account_id=? OR ? IS NULL)",
            (order_id, account_id, account_id),
        ).fetchone()
        if row is None:
            raise LookupError("order_not_found")
        return row

    def grant_friend_access(self, account_id, days):
        if type(days) is not int or not 1 <= days <= 365:
            raise ValueError("invalid_access_duration")
        expires_at = int(time.time()) + days * 86400
        with self.transaction(write=True) as db:
            account = db.execute(
                "SELECT id FROM accounts WHERE id=? AND role='buyer'", (account_id,)
            ).fetchone()
            if account is None:
                raise LookupError("buyer_not_found")
            db.execute(
                """INSERT INTO friend_access VALUES(?,?)
                   ON CONFLICT(account_id) DO UPDATE SET expires_at =
                   MAX(friend_access.expires_at, excluded.expires_at)""",
                (account_id, expires_at),
            )
            return self._entitlement(db, account_id)

    @staticmethod
    def _entitlement(db, account_id):
        row = db.execute(
            """SELECT MAX(expires_at) AS expires_at FROM (
                SELECT expires_at FROM entitlements WHERE account_id=?
                UNION ALL
                SELECT expires_at FROM friend_access WHERE account_id=?
            )""",
            (account_id, account_id),
        ).fetchone()
        expires_at = row["expires_at"]
        return {"active": expires_at is not None and expires_at > int(time.time()),
                "expires_at": expires_at, "demo": True}

    @staticmethod
    def _public(row):
        order = dict(row)
        order.pop("request_id")
        order.pop("reference")
        base = CATALOG[order["plan"]]["amount_kopeks"]
        order["base_amount_kopeks"] = base
        order["discount_percent"] = 10 if order["amount_kopeks"] < base else 0
        return {**order, "demo": True}

    def entitlement(self, account_id):
        with self.transaction() as db:
            return self._entitlement(db, account_id)

    def referral(self, account_id):
        with self.transaction(write=True) as db:
            account = db.execute("SELECT 1 FROM accounts WHERE id=? AND role='buyer'",
                                 (account_id,)).fetchone()
            if not account:
                raise LookupError("buyer_not_found")
            db.execute("INSERT OR IGNORE INTO referral_codes VALUES(?,?)",
                       (account_id, secrets.token_hex(12).upper()))
            code = db.execute("SELECT code FROM referral_codes WHERE account_id=?",
                              (account_id,)).fetchone()[0]
            invited = db.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=?",
                                 (account_id,)).fetchone()[0]
            purchases = db.execute(
                """SELECT COUNT(*) FROM referrals r JOIN orders o ON o.order_id=r.qualified_order
                   WHERE r.inviter_id=? AND o.status='confirmed'""", (account_id,),
            ).fetchone()[0]
            rewards = db.execute(
                """SELECT COUNT(*) FROM referral_rewards r JOIN orders o ON o.order_id=r.source_order
                   WHERE r.account_id=? AND r.consumed_order IS NULL AND o.status='confirmed'""",
                (account_id,),
            ).fetchone()[0]
            bound = db.execute("SELECT 1 FROM referrals WHERE invited_id=?", (account_id,)).fetchone()
            return {"code": code, "invited": invited, "purchases": purchases,
                    "available_discounts": rewards, "discount_percent": 10 if rewards else 0,
                    "referrer_applied": bool(bound), "demo": True}

    def apply_referral(self, account_id, code):
        if not isinstance(code, str) or not re.fullmatch(r"[A-F0-9]{24}", code):
            raise ValueError("invalid_referral_code")
        with self.transaction(write=True) as db:
            inviter = db.execute("SELECT account_id FROM referral_codes WHERE code=?", (code,)).fetchone()
            if inviter is None or inviter[0] == account_id:
                raise ValueError("invalid_referral_code")
            previous = db.execute("SELECT inviter_id FROM referrals WHERE invited_id=?", (account_id,)).fetchone()
            if previous:
                if previous[0] != inviter[0]:
                    raise Conflict("referral_already_applied")
            else:
                if db.execute("SELECT 1 FROM orders WHERE account_id=?", (account_id,)).fetchone():
                    raise Conflict("referral_requires_new_customer")
                # Disallow direct and indirect invitation loops.
                ancestor = inviter[0]
                while ancestor:
                    if ancestor == account_id:
                        raise Conflict("referral_cycle")
                    row = db.execute("SELECT inviter_id FROM referrals WHERE invited_id=?", (ancestor,)).fetchone()
                    ancestor = row[0] if row else None
                db.execute("INSERT INTO referrals(invited_id,inviter_id) VALUES(?,?)", (account_id, inviter[0]))
        return self.referral(account_id)

    def get(self, order_id, account_id):
        with self.transaction() as db:
            return self._public(self._order(db, order_id, account_id))

    def create(self, account_id, plan, method, request_id):
        if (not isinstance(plan, str) or plan not in CATALOG or method not in METHODS
                or not isinstance(request_id, str) or not IDENTIFIER.fullmatch(request_id)):
            raise ValueError("invalid_order")
        tariff = CATALOG[plan]
        with self.transaction(write=True) as db:
            row = db.execute("SELECT * FROM orders WHERE account_id=? AND request_id=?",
                             (account_id, request_id)).fetchone()
            if row is not None:
                if (row["plan"], row["method"]) != (plan, method):
                    raise Conflict("idempotency_conflict")
                return self._public(row)
            order_id = secrets.token_hex(16).upper()
            reward = db.execute(
                """SELECT r.source_order FROM referral_rewards r JOIN orders o ON o.order_id=r.source_order
                   WHERE r.account_id=? AND r.consumed_order IS NULL AND o.status='confirmed'
                   ORDER BY o.confirmed_at,o.rowid LIMIT 1""", (account_id,),
            ).fetchone()
            amount = tariff["amount_kopeks"] * (90 if reward else 100) // 100
            db.execute("""INSERT INTO orders
                       (order_id,account_id,request_id,plan,days,amount_kopeks,currency,
                        method,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (order_id, account_id, request_id, plan, tariff["hours"] // 24,
                        amount, "RUB", method, "awaiting_payment", int(time.time())))
            if reward:
                db.execute("UPDATE referral_rewards SET consumed_order=? WHERE source_order=? AND account_id=?",
                           (order_id, reward[0], account_id))
            return self._public(self._order(db, order_id, account_id))

    def list_orders(self, account_id=None, status="", query="", offset=0):
        with self.transaction() as db:
            rows = db.execute(
                """SELECT * FROM orders WHERE (account_id=? OR ? IS NULL)
                   AND (status=? OR ?='')
                   AND (instr(upper(order_id), upper(?))>0 OR instr(account_id, ?)>0 OR ?='')
                   ORDER BY created_at DESC, rowid DESC LIMIT 50 OFFSET ?""",
                (account_id, account_id, status, status, query, query, query, offset),
            )
            return [self._public(row) for row in rows]

    def detail(self, order_id):
        with self.transaction() as db:
            order = self._order(db, order_id)
            events = db.execute(
                "SELECT actor,action,reason,occurred_at FROM events WHERE order_id=? ORDER BY id",
                (order_id,),
            )
            return {**self._public(order), "reference": order["reference"],
                    "events": [dict(event) for event in events]}

    def submit(self, account_id, order_id):
        with self.transaction(write=True) as db:
            order = self._order(db, order_id, account_id)
            if order["status"] == "awaiting_payment":
                db.execute("UPDATE orders SET status='under_review' WHERE order_id=?", (order_id,))
            return self._public(self._order(db, order_id, account_id))

    def review(self, actor, order_id, action, reason, reference="", amount=None):
        target, event, sources = {
            "confirm": ("confirmed", "payment_confirmed", PENDING),
            "reject": ("rejected", "order_rejected", PENDING),
            "refund": ("refunded", "payment_refunded", ("confirmed",)),
        }[action]
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 200:
            raise ValueError("reason_required")
        with self.transaction(write=True) as db:
            if not db.execute("SELECT 1 FROM accounts WHERE id=? AND role='owner'", (actor,)).fetchone():
                raise PermissionError("owner_required")
            order = self._order(db, order_id)
            if action == "confirm":
                if (order["method"] != "bank_transfer"
                        or not isinstance(reference, str) or not REFERENCE.fullmatch(reference)
                        or type(amount) is not int or amount != order["amount_kopeks"]):
                    raise ValueError("invalid_demo_reconciliation")
                if order["reference"] and order["reference"] != reference:
                    raise Conflict("reference_conflict")
            if order["status"] == target:
                return
            if order["status"] not in sources:
                raise Conflict("invalid_transition")
            now = int(time.time())
            if action == "confirm":
                reward = db.execute(
                    """SELECT o.status FROM referral_rewards r JOIN orders o ON o.order_id=r.source_order
                       WHERE r.consumed_order=?""", (order_id,),
                ).fetchone()
                if reward and reward[0] != "confirmed":
                    raise Conflict("referral_discount_revoked")
                used = db.execute("SELECT 1 FROM orders WHERE reference=?", (reference,)).fetchone()
                if used:
                    raise Conflict("reference_already_used")
                db.execute("UPDATE orders SET reference=?,confirmed_at=? WHERE order_id=?",
                           (reference, now, order_id))
            db.execute("UPDATE orders SET status=? WHERE order_id=?", (target, order_id))
            db.execute("INSERT INTO events(order_id,actor,action,reason,occurred_at) VALUES(?,?,?,?,?)",
                       (order_id, actor, event, reason.strip(), now))
            if action in ("confirm", "refund"):
                self._update_entitlement(db, order["account_id"])
            if action == "confirm":
                self._qualify_referral(db, order)
            elif action in ("reject", "refund"):
                # An abandoned/reversed purchase does not consume a discount. A refunded
                # source cannot supply new discounts (queries require confirmed status).
                db.execute("UPDATE referral_rewards SET consumed_order=NULL WHERE consumed_order=?", (order_id,))

    @staticmethod
    def _qualify_referral(db, order):
        account_id, order_id = order["account_id"], order["order_id"]
        referral = db.execute("SELECT * FROM referrals WHERE invited_id=?", (account_id,)).fetchone()
        if referral is None or referral["qualified_order"]:
            return
        # Only the first ever confirmed payment qualifies, including when an earlier
        # payment was refunded. Free access and client 'paid' clicks never qualify.
        count = db.execute(
            """SELECT COUNT(*) FROM events e JOIN orders o ON o.order_id=e.order_id
               WHERE o.account_id=? AND e.action='payment_confirmed'""", (account_id,),
        ).fetchone()[0]
        if count != 1:
            return
        db.execute("UPDATE referrals SET qualified_order=? WHERE invited_id=?", (order_id, account_id))
        for beneficiary in (account_id, referral["inviter_id"]):
            db.execute("INSERT INTO referral_rewards(source_order,account_id) VALUES(?,?)", (order_id, beneficiary))

    @staticmethod
    def _update_entitlement(db, account_id):
        grants = db.execute(
            """SELECT confirmed_at,days FROM orders WHERE account_id=? AND status='confirmed'
               ORDER BY confirmed_at, rowid""", (account_id,),
        )
        expiry = 0
        for grant in grants:
            expiry = max(expiry, grant["confirmed_at"]) + grant["days"] * 86400
        if expiry:
            db.execute(
                """INSERT INTO entitlements VALUES(?,?) ON CONFLICT(account_id)
                   DO UPDATE SET expires_at=excluded.expires_at""", (account_id, expiry),
            )
        else:
            db.execute("DELETE FROM entitlements WHERE account_id=?", (account_id,))


class Conflict(Exception):
    pass
