"""Fortnite Pirate Token: Telegram Stars store + license API (Python 3.11+, stdlib).

This service must run on an always-online machine. TLS termination must be
configured outside this app (e.g. reverse proxy); never expose raw HTTP publicly.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
PLAN_DAYS = {"day": 1, "three_days": 3, "week": 7, "month": 30}
PLAN_LABELS = {"day": "1 день", "three_days": "3 дня", "week": "7 дней", "month": "30 дней"}
KEY_FORMAT = re.compile(r"^FPT-([0-9A-F]{16})-([0-9A-F]{32})$")
DEVICE_FORMAT = re.compile(r"^[A-Za-z0-9_-]{20,100}$")


def env_file(path: Path = ROOT / ".env") -> None:
    """Minimal dotenv loader: only KEY=VALUE, no shell execution."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            os.environ.setdefault(key, val)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    license_secret: str
    admin_id: int
    public_base_url: str
    listen_host: str
    listen_port: int
    database_path: Path
    installer_path: Path
    prices: dict[str, int]
    support_username: str
    terms_url: str
    terms_version: str
    sales_enabled: bool
    telegram_test_mode: bool

    @classmethod
    def from_env(cls) -> "Settings":
        env_file()
        prices = {plan: int(os.environ.get("PLAN_" + plan.upper() + "_STARS", "0")) for plan in PLAN_DAYS}
        base_url = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
        if base_url and (urlsplit(base_url).scheme != "https" or not urlsplit(base_url).netloc):
            raise ValueError("PUBLIC_BASE_URL должен начинаться с https://")
        bot_token = os.environ.get("BOT_TOKEN", "")
        secret = os.environ.get("LICENSE_SECRET", "")
        admin_id = int(os.environ.get("ADMIN_USER_ID", "0"))
        if not bot_token or len(secret) < 32 or admin_id <= 0:
            raise ValueError("Укажи BOT_TOKEN, ADMIN_USER_ID и LICENSE_SECRET (32+ символов) в .env")
        if any(price < 0 for price in prices.values()):
            raise ValueError("Цены Stars не могут быть отрицательными")
        terms_url = os.environ.get("TERMS_URL", "").strip()
        sales_enabled = os.environ.get("SALES_ENABLED", "0") == "1"
        if sales_enabled and (not base_url or not terms_url.startswith("https://")):
            raise ValueError("Для приёма оплат укажи PUBLIC_BASE_URL, TERMS_URL (HTTPS)")
        db = Path(os.environ.get("DB_PATH", "private/licenses.db"))
        installer = Path(os.environ.get("INSTALLER_PATH", "installer/EasyRewards_Setup.exe"))
        return cls(
            bot_token, secret, admin_id, base_url,
            os.environ.get("LISTEN_HOST", "127.0.0.1"),
            int(os.environ.get("LISTEN_PORT", "8765")),
            db if db.is_absolute() else ROOT / db,
            installer if installer.is_absolute() else ROOT / installer,
            prices, os.environ.get("SUPPORT_USERNAME", ""),
            terms_url, os.environ.get("TERMS_VERSION", "v1"),
            sales_enabled, os.environ.get("TELEGRAM_TEST_MODE", "0") == "1",
        )


def format_expiration(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


class Store:
    def __init__(self, db_path: Path, secret: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.secret = secret.encode("utf-8")
        self.lock = threading.RLock()
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    tg_id INTEGER PRIMARY KEY,
                    key_id TEXT NOT NULL UNIQUE,
                    expires_at INTEGER NOT NULL DEFAULT 0,
                    device_hash TEXT
                );
                CREATE TABLE IF NOT EXISTS invoices (
                    payload TEXT PRIMARY KEY,
                    tg_id INTEGER NOT NULL,
                    plan TEXT NOT NULL,
                    stars INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    charge_id TEXT UNIQUE
                );
                CREATE TABLE IF NOT EXISTS payments (
                    charge_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL UNIQUE,
                    tg_id INTEGER NOT NULL,
                    seconds INTEGER NOT NULL,
                    stars INTEGER NOT NULL,
                    purchased_at INTEGER NOT NULL,
                    refunded_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS agreements (
                    tg_id INTEGER PRIMARY KEY,
                    terms_version TEXT NOT NULL,
                    accepted_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS downloads (
                    token TEXT PRIMARY KEY,
                    tg_id INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    used_at INTEGER
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _user(self, db, tg_id: int) -> sqlite3.Row:
        row = db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        if row is None:
            db.execute("INSERT INTO users(tg_id,key_id) VALUES(?,?)", (tg_id, secrets.token_hex(8).upper()))
            row = db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        return row

    def key_for(self, row: sqlite3.Row) -> str:
        suffix = hmac.new(self.secret, f"{row['tg_id']}:{row['key_id']}".encode(), hashlib.sha256).hexdigest()[:32].upper()
        return f"FPT-{row['key_id']}-{suffix}"

    def accept_terms(self, tg_id: int, version: str):
        with self.lock, self.connection() as db:
            db.execute("INSERT INTO agreements VALUES(?,?,?) ON CONFLICT(tg_id) DO UPDATE SET terms_version=excluded.terms_version, accepted_at=excluded.accepted_at",
                       (tg_id, version, int(time.time())))

    def terms_accepted(self, tg_id: int, version: str) -> bool:
        with self.lock, self.connection() as db:
            row = db.execute("SELECT terms_version FROM agreements WHERE tg_id=?", (tg_id,)).fetchone()
            return bool(row and row["terms_version"] == version)

    def create_invoice(self, tg_id: int, plan: str, stars: int) -> str:
        if plan not in PLAN_DAYS or stars <= 0:
            raise ValueError("Тариф недоступен")
        payload = secrets.token_hex(16)
        with self.lock, self.connection() as db:
            db.execute("INSERT INTO invoices VALUES(?,?,?,?,?,NULL)", (payload, tg_id, plan, stars, int(time.time())))
        return payload

    def invoice_valid(self, payload: str, tg_id: int, currency: str, stars: int) -> bool:
        with self.lock, self.connection() as db:
            invoice = db.execute("SELECT * FROM invoices WHERE payload=?", (payload,)).fetchone()
            return bool(invoice and currency == "XTR" and invoice["tg_id"] == tg_id
                        and invoice["stars"] == stars and invoice["charge_id"] is None
                        and int(time.time()) - invoice["created_at"] < 86400)

    def apply_payment(self, payload: str, tg_id: int, currency: str, stars: int, charge: str):
        if not charge:
            raise ValueError("Платёж без идентификатора")
        now = int(time.time())
        with self.lock, self.connection() as db:
            existing = db.execute("SELECT * FROM payments WHERE charge_id=?", (charge,)).fetchone()
            if existing:
                if existing["tg_id"] != tg_id or existing["payload"] != payload:
                    raise ValueError("Конфликт идентификатора платежа")
                row = db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
                return self.key_for(row), row["expires_at"], False
            invoice = db.execute("SELECT * FROM invoices WHERE payload=?", (payload,)).fetchone()
            if not invoice or invoice["tg_id"] != tg_id or currency != "XTR" or invoice["stars"] != stars:
                raise ValueError("Несовпадение данных оплаты")
            if invoice["charge_id"] is not None:
                raise ValueError("Счёт уже оплачен другим платежом")
            seconds = PLAN_DAYS[invoice["plan"]] * 86400
            user = self._user(db, tg_id)
            expiry = max(now, user["expires_at"]) + seconds
            db.execute("UPDATE users SET expires_at=? WHERE tg_id=?", (expiry, tg_id))
            db.execute("UPDATE invoices SET charge_id=? WHERE payload=?", (charge, payload))
            db.execute("INSERT INTO payments VALUES(?,?,?,?,?,?,NULL)", (charge, payload, tg_id, seconds, stars, now))
            return self.key_for(user), expiry, True

    def grant(self, tg_id: int, days: int):
        if days <= 0 or days > 3650:
            raise ValueError("Дни должны быть в диапазоне 1..3650")
        with self.lock, self.connection() as db:
            row = self._user(db, tg_id)
            expiry = max(int(time.time()), row["expires_at"]) + days * 86400
            db.execute("UPDATE users SET expires_at=? WHERE tg_id=?", (expiry, tg_id))
            return self.key_for(row), expiry

    def user_status(self, tg_id: int):
        with self.lock, self.connection() as db:
            row = db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
            if not row:
                return None
            return {"key": self.key_for(row), "expires_at": row["expires_at"], "device_bound": bool(row["device_hash"])}

    def validate(self, key: str, device_id: str):
        """Online source of truth; activation binds first random device ID."""
        if not isinstance(key, str) or not isinstance(device_id, str):
            return {"ok": False, "error": "invalid_input"}
        match = KEY_FORMAT.fullmatch(key.strip())
        if not match or not DEVICE_FORMAT.fullmatch(device_id):
            return {"ok": False, "error": "invalid_key_or_device"}
        key_id, signature = match.groups()
        hashed_device = hashlib.sha256(device_id.encode("utf-8")).hexdigest()
        with self.lock, self.connection() as db:
            row = db.execute("SELECT * FROM users WHERE key_id=?", (key_id,)).fetchone()
            if not row or not hmac.compare_digest(self.key_for(row), key.strip()):
                return {"ok": False, "error": "invalid_key"}
            if row["expires_at"] <= int(time.time()):
                return {"ok": False, "error": "expired", "expires_at": row["expires_at"]}
            if row["device_hash"] and not hmac.compare_digest(row["device_hash"], hashed_device):
                return {"ok": False, "error": "another_device"}
            if row["device_hash"] is None:
                db.execute("UPDATE users SET device_hash=? WHERE tg_id=? AND device_hash IS NULL",
                           (hashed_device, row["tg_id"]))
            return {"ok": True, "expires_at": row["expires_at"], "seconds_left": max(0, row["expires_at"] - int(time.time()))}

    def reset_device(self, tg_id: int) -> bool:
        with self.lock, self.connection() as db:
            r = db.execute("UPDATE users SET device_hash=NULL WHERE tg_id=?", (tg_id,))
            return bool(r.rowcount)

    def create_download(self, tg_id: int) -> str | None:
        with self.lock, self.connection() as db:
            user = db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
            if not user or user["expires_at"] <= int(time.time()):
                return None
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO downloads VALUES(?,?,?,NULL)", (token, tg_id, int(time.time()) + 900))
            return token

    def consume_download(self, token: str) -> bool:
        with self.lock, self.connection() as db:
            row = db.execute("SELECT * FROM downloads WHERE token=?", (token,)).fetchone()
            if not row or row["used_at"] is not None or row["expires_at"] <= int(time.time()):
                return False
            user = db.execute("SELECT expires_at FROM users WHERE tg_id=?", (row["tg_id"],)).fetchone()
            if not user or user["expires_at"] <= int(time.time()):
                return False
            db.execute("UPDATE downloads SET used_at=? WHERE token=?", (int(time.time()), token))
            return True

    def payment_user(self, charge: str):
        with self.lock, self.connection() as db:
            return db.execute("SELECT * FROM payments WHERE charge_id=?", (charge,)).fetchone()

    def record_refund(self, charge: str):
        with self.lock, self.connection() as db:
            payment = db.execute("SELECT * FROM payments WHERE charge_id=?", (charge,)).fetchone()
            if not payment or payment["refunded_at"]:
                return False
            row = db.execute("SELECT expires_at FROM users WHERE tg_id=?", (payment["tg_id"],)).fetchone()
            if row:
                db.execute("UPDATE users SET expires_at=? WHERE tg_id=?",
                           (max(int(time.time()), row["expires_at"] - payment["seconds"]), payment["tg_id"]))
            db.execute("UPDATE payments SET refunded_at=? WHERE charge_id=?", (int(time.time()), charge))
            return True


class TelegramAPI:
    def __init__(self, token, test_mode: bool = False):
        self.url = f"https://api.telegram.org/bot{token}/" + ("test/" if test_mode else "")

    def call(self, method: str, data: dict | None = None, timeout: int = 35):
        payload = json.dumps(data or {}, ensure_ascii=False).encode("utf-8")
        req = request.Request(self.url + method, data=payload, headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                result = json.load(resp)
        except HTTPError as ex:
            raise RuntimeError(f"Telegram {method} HTTP {ex.code}") from ex
        if not result.get("ok"):
            raise RuntimeError(f"Telegram {method}: {result.get('description', 'error')}")
        return result["result"]


class TelegramShop:
    def __init__(self, settings: Settings, store: Store, api: TelegramAPI):
        self.settings, self.store, self.api = settings, store, api

    def send(self, chat: int, text: str, keyboard=None):
        data = {"chat_id": chat, "text": text}
        if keyboard:
            data["reply_markup"] = {"inline_keyboard": keyboard}
        return self.api.call("sendMessage", data)

    def plans(self):
        return [[{"text": f"{PLAN_LABELS[p]} — {price} ⭐", "callback_data": "buy:" + p}]
                for p, price in self.settings.prices.items() if price > 0]

    def send_invoice(self, chat_id: int, user_id: int, plan: str):
        if not self.settings.sales_enabled:
            self.send(chat_id, "Продажи пока закрыты: разработчик не завершил настройку и тестирование.")
            return
        if not self.settings.installer_path.is_file():
            self.send(chat_id, "Установщик пока недоступен. Свяжись с поддержкой: /paysupport")
            return
        if not self.store.terms_accepted(user_id, self.settings.terms_version):
            self.send(chat_id, "Перед оплатой прочитай условия: " + self.settings.terms_url
                      + "\nПосле этого подтверди согласие:",
                      [[{"text": "✅ Принимаю условия", "callback_data": "accept:" + plan}]])
            return
        stars = self.settings.prices.get(plan, 0)
        if stars <= 0:
            self.send(chat_id, "Этот тариф пока не настроен.")
            return
        payload = self.store.create_invoice(user_id, plan, stars)
        self.api.call("sendInvoice", {
            "chat_id": chat_id,
            "title": "Fortnite Pirate Token",
            "description": "Доступ к утилите на " + PLAN_LABELS[plan],
            "payload": payload,
            "provider_token": "",
            "currency": "XTR",
            "prices": [{"label": "Подписка " + PLAN_LABELS[plan], "amount": stars}],
            "start_parameter": payload,
        })

    def customer_status(self, chat_id: int, tg_id: int):
        data = self.store.user_status(tg_id)
        if not data or data["expires_at"] <= int(time.time()):
            self.send(chat_id, "Активной подписки нет. Выбери /plans для покупки.")
            return
        self.send(chat_id, "🔑 Лицензионный ключ:\n" + data["key"]
                  + "\n\nПодписка до " + format_expiration(data["expires_at"])
                  + "\nУстройство: " + ("привязано" if data["device_bound"] else "ещё не привязано")
                  + "\nНе публикуй ключ и не передавай его другим людям.")

    def customer_download(self, chat_id: int, tg_id: int):
        if not self.settings.public_base_url or not self.settings.installer_path.is_file():
            self.send(chat_id, "Загрузка пока не подключена разработчиком. Подписку можно проверить: /license. Поддержка: /paysupport")
            return
        token = self.store.create_download(tg_id)
        if not token:
            self.send(chat_id, "Нужна активная подписка. /plans")
            return
        self.send(chat_id, "📦 Скачать установщик (ссылка действует 15 минут, один раз):\n"
                  + self.settings.public_base_url + "/download/" + token)

    def handle_update(self, u: dict):
        pq = u.get("pre_checkout_query")
        if pq:
            valid = (self.settings.sales_enabled and
                     self.store.terms_accepted(int(pq["from"]["id"]), self.settings.terms_version) and
                     self.store.invoice_valid(str(pq.get("invoice_payload", "")),
                                             int(pq["from"]["id"]), str(pq.get("currency", "")),
                                             int(pq.get("total_amount", -1))))
            self.api.call("answerPreCheckoutQuery", {
                "pre_checkout_query_id": pq["id"], "ok": valid,
                **({} if valid else {"error_message": "Счёт недействителен. Сформируйте новый через /plans."})
            }, timeout=5)
            return
        cb = u.get("callback_query")
        if cb:
            self.api.call("answerCallbackQuery", {"callback_query_id": cb["id"]})
            user_id = int(cb["from"]["id"])
            chat = cb.get("message", {}).get("chat", {})
            if chat.get("type") == "private" and chat.get("id") == user_id:
                action = str(cb.get("data", ""))
                if action.startswith("accept:"):
                    plan = action[7:]
                    if plan in PLAN_DAYS and self.settings.terms_url:
                        self.store.accept_terms(user_id, self.settings.terms_version)
                        self.send_invoice(user_id, user_id, plan)
                if action.startswith("buy:"):
                    plan = action[4:]
                    if plan in PLAN_DAYS:
                        self.send_invoice(user_id, user_id, plan)
            return
        msg = u.get("message")
        if not msg or msg.get("chat", {}).get("type") != "private":
            return
        chat_id, tg_id = int(msg["chat"]["id"]), int(msg["from"]["id"])
        payment = msg.get("successful_payment")
        if payment:
            key, expires, new = self.store.apply_payment(
                str(payment.get("invoice_payload", "")), tg_id,
                str(payment.get("currency", "")), int(payment.get("total_amount", -1)),
                str(payment.get("telegram_payment_charge_id", "")))
            self.send(chat_id, "✅ Оплата подтверждена! " + ("Подписка активирована." if new else "Подписка уже учтена.")
                      + "\n\n🔑 Твой ключ:\n" + key + "\n\nДействует до " + format_expiration(expires)
                      + "\n\nДля установщика нажми /download. Для проверки срока — /license.")
            return
        words = str(msg.get("text", "")).strip().split()
        if not words:
            return
        command = words[0].split("@")[0].lower()
        if command == "/demo":
            self.send(chat_id, "ДЕМО: покупка отключена. В Telegram цифровой доступ можно продавать только через Stars. "
                      "Банковские карты, СБП, переводы и скины будут оформляться отдельно на сайте/в лаунчере. "
                      "Никакой платёж сейчас не требуется.")
        elif command in ("/start", "/plans"):
            kb = self.plans() if self.settings.sales_enabled else []
            self.send(chat_id,
                      "🏴‍☠️ Fortnite Pirate Token\nПокупка цифровой подписки за Telegram Stars."
                      "\n\nВыбери тариф. После подтверждения оплаты придут ключ и ссылка на программу."
                      "\n/plans — тарифы, /terms — условия, /license — лицензия, /download — установщик, /paysupport — поддержка."
                      if kb else "Fortnite Pirate Token — демонстрация подписок. Продажи сейчас отключены. "
                      "Выбор тарифов: 1 / 3 / 7 / 30 дней. /demo — как будет работать оплата, "
                      "/license — моя лицензия, /paysupport — поддержка. "
                      "Не отправляй деньги или скины.", kb)
        elif command == "/terms":
            self.send(chat_id, "Условия покупки и использования: "
                      + (self.settings.terms_url or "владелец пока не опубликовал")
                      + "\nПеред оплатой потребуется подтверждение согласия.")
        elif command == "/license":
            self.customer_status(chat_id, tg_id)
        elif command == "/download":
            self.customer_download(chat_id, tg_id)
        elif command == "/paysupport":
            explanation = " ".join(words[1:])[:700]
            self.send(chat_id, "Заявка в поддержку принята. Укажи проблему командой /paysupport описание проблемы."
                      + ("\nКонтакт: @" + self.settings.support_username.lstrip("@") if self.settings.support_username else ""))
            if explanation:
                self.send(self.settings.admin_id, f"🆘 Поддержка, Telegram ID {tg_id}:\n{explanation}")
        elif command == "/buy" and len(words) == 2 and words[1] in PLAN_DAYS:
            self.send_invoice(chat_id, tg_id, words[1])
        elif command == "/grant" and tg_id == self.settings.admin_id and len(words) == 3:
            key, expiry = self.store.grant(int(words[1]), int(words[2]))
            self.send(chat_id, f"Выдано: {words[1]} до {format_expiration(expiry)}\n{key}")
        elif command == "/resetdevice" and tg_id == self.settings.admin_id and len(words) == 2:
            ok = self.store.reset_device(int(words[1]))
            self.send(chat_id, "Привязка сброшена." if ok else "Пользователь не найден.")
        elif command == "/refund" and tg_id == self.settings.admin_id and len(words) == 2:
            charge = words[1]
            p = self.store.payment_user(charge)
            if not p or p["refunded_at"]:
                self.send(chat_id, "Платёж не найден или уже возвращён.")
            else:
                self.api.call("refundStarPayment", {"user_id": p["tg_id"], "telegram_payment_charge_id": charge})
                self.store.record_refund(charge)
                self.send(chat_id, f"Возврат выполнен для Telegram ID {p['tg_id']}; срок лицензии пересчитан.")
        elif command == "/help":
            self.send(chat_id, "/start /plans /demo /terms /license /download /paysupport описание проблемы")

    def run_forever(self):
        offset = 0
        self.api.call("deleteWebhook", {"drop_pending_updates": False})
        print("Telegram shop started. Don't start multiple bot pollers.", flush=True)
        while True:
            try:
                updates = self.api.call("getUpdates", {
                    "offset": offset, "timeout": 25,
                    "allowed_updates": ["message", "callback_query", "pre_checkout_query"],
                }, timeout=35)
                for update in updates:
                    self.handle_update(update)
                    offset = int(update["update_id"]) + 1
            except (RuntimeError, URLError, TimeoutError, ValueError, KeyError, sqlite3.Error) as exc:
                print("Bot error (will retry):", type(exc).__name__, str(exc)[:200], flush=True)
                time.sleep(3)


def serve(settings: Settings, store: Store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FPTLicense/1.0"

        def log_message(self, fmt, *args):
            # Don't log license keys, one-time download URLs, or Telegram secrets.
            pass

        def send_json(self, obj, status=200):
            raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            if self.path not in ("/v1/activate", "/v1/check"):
                return self.send_json({"ok": False, "error": "not_found"}, 404)
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                return self.send_json({"ok": False, "error": "content_type"}, 415)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 4096:
                    return self.send_json({"ok": False, "error": "payload_size"}, 413)
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                result = store.validate(obj.get("key", ""), obj.get("device_id", ""))
                return self.send_json(result, 200 if result["ok"] else 403)
            except (ValueError, UnicodeDecodeError, AttributeError):
                return self.send_json({"ok": False, "error": "bad_json"}, 400)

        def do_GET(self):
            if self.path == "/health":
                return self.send_json({"ok": True, "service": "license"})
            prefix = "/download/"
            if not self.path.startswith(prefix):
                return self.send_json({"ok": False, "error": "not_found"}, 404)
            token = self.path[len(prefix):]
            if not re.fullmatch(r"[A-Za-z0-9_-]{32,80}", token):
                return self.send_json({"ok": False, "error": "invalid_link"}, 404)
            installer = settings.installer_path
            if not installer.is_file():
                return self.send_json({"ok": False, "error": "installer_unavailable"}, 503)
            if not store.consume_download(token):
                return self.send_json({"ok": False, "error": "link_expired_or_used"}, 403)
            size = installer.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="FortnitePirateTokenSetup.exe"')
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with installer.open("rb") as fh:
                while chunk := fh.read(1024 * 256):
                    self.wfile.write(chunk)

    http = ThreadingHTTPServer((settings.listen_host, settings.listen_port), Handler)
    print(f"License API listening at http://{settings.listen_host}:{settings.listen_port}", flush=True)
    try:
        http.serve_forever()
    finally:
        http.server_close()


def main():
    settings = Settings.from_env()
    store = Store(settings.database_path, settings.license_secret)
    api = TelegramAPI(settings.bot_token, settings.telegram_test_mode)
    # Test credentials before starting server, without exposing token in logs.
    me = api.call("getMe")
    print("Authenticated Telegram bot: @" + str(me.get("username", "?")), flush=True)
    threading.Thread(target=serve, args=(settings, store), daemon=True, name="license-http").start()
    TelegramShop(settings, store, api).run_forever()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, ValueError) as exc:
        print("Stopped:", str(exc), flush=True)