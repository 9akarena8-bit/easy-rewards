"""Loopback-only order API and private owner console for synthetic payments."""
import argparse
from collections import deque
from hmac import compare_digest
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, urlencode, urlsplit

from .orders import CATALOG, METHODS, Conflict, Orders

COOKIE = "merchant_demo_owner"
STATUSES = {
    "": "Все", "awaiting_payment": "Новые", "under_review": "Ожидают",
    "confirmed": "Подтверждены", "rejected": "Отклонены", "refunded": "Возвращены",
}


class DemoServer(ThreadingHTTPServer):
    def __init__(self, port, store):
        super().__init__(("127.0.0.1", port), Handler)
        self.store = store
        self.host = f"127.0.0.1:{self.server_port}"
        self.origin = f"http://{self.host}"
        self.rate_lock = Lock()
        self.attempts = {"login": deque(), "write": deque()}

    def limited(self, kind):
        with self.rate_lock:
            now = monotonic()
            attempts = self.attempts[kind]
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            limit = 12 if kind == "login" else 120
            if len(attempts) >= limit:
                return True
            attempts.append(now)
            return False


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def respond(self, status, data, *, cookie=None):
        html = isinstance(data, str)
        body = (data if html else json.dumps(data)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ("text/html" if html else "application/json") + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
        self.send_header("Content-Length", str(len(body)))
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, path, *, cookie=None):
        self.send_response(303)
        self.send_header("Location", path)
        self.send_header("Cache-Control", "no-store")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def body(self, content_type):
        if self.headers.get_content_type() != content_type or self.headers.get("Transfer-Encoding"):
            raise ValueError("invalid_content_type")
        size = int(self.headers.get("Content-Length", 0))
        if not 0 < size <= 8192:
            raise ValueError("invalid_body_size")
        raw = self.rfile.read(size).decode("utf-8")
        if content_type == "application/json":
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("invalid_body")
            return data
        return {key: values[0] for key, values in parse_qs(raw, max_num_fields=12).items()}

    def dispatch(self):
        try:
            if self.headers.get("Host") != self.server.host:
                raise PermissionError("invalid_host")
            origin = self.headers.get("Origin")
            if origin and origin != self.server.origin:
                raise PermissionError("invalid_origin")
            url = urlsplit(self.path)
            path = url.path.strip("/").split("/")
            query = parse_qs(url.query, max_num_fields=8)
            if path[0] == "admin":
                self.admin(path[1:], query, origin)
            elif path[:2] == ["api", "v1"]:
                self.api(path[2:], query)
            else:
                raise LookupError("not_found")
        except PermissionError as exc:
            self.respond(403, {"error": str(exc)})
        except LookupError as exc:
            self.respond(404, {"error": str(exc)})
        except Conflict as exc:
            self.respond(409, {"error": str(exc)})
        except (ValueError, TypeError):
            self.respond(400, {"error": "invalid_request"})
        except sqlite3.Error:
            self.respond(503, {"error": "database_unavailable"})

    def throttle(self, kind):
        if self.server.limited(kind):
            self.respond(429, {"error": "rate_limited"})
            return True
        return False

    def api(self, path, query):
        store = self.server.store
        post = self.command == "POST"
        if not post and path == ["catalog"]:
            self.respond(200, {"demo": True, "sales_enabled": False, "currency": "RUB",
                               "plans": list(CATALOG.values()), "methods": METHODS})
            return
        if post and path == ["session"]:
            if not self.throttle("login"):
                data = self.body("application/json")
                credential = data.get("credential")
                if not isinstance(credential, str):
                    raise ValueError("invalid_credential")
                token = store.login(credential, "buyer")
                self.respond(200, {"token": token, "expires_in": 3600})
            return
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise PermissionError("authentication_required")
        account = store.actor(token, "buyer")["id"]
        if post and self.throttle("write"):
            return
        if path == ["session", "logout"] and post:
            store.logout(token)
            result = {"ok": True}
        elif path == ["entitlement"] and not post:
            result = store.entitlement(account)
        elif path == ["referral"] and not post:
            result = store.referral(account)
        elif path == ["referral"] and post:
            data = self.body("application/json")
            if set(data) != {"code"}:
                raise ValueError("invalid_fields")
            result = store.apply_referral(account, data["code"])
        elif path == ["orders"] and post:
            data = self.body("application/json")
            if set(data) != {"plan", "method", "request_id"}:
                raise ValueError("invalid_fields")
            result = store.create(account, **data)
        elif path == ["orders"] and not post:
            result = {"orders": store.list_orders(account, offset=offset_from(query))}
        elif path[:1] == ["orders"] and len(path) == 2 and not post:
            result = store.get(path[1], account)
        elif path[:1] == ["orders"] and len(path) == 3 and path[2] == "submit" and post:
            result = store.submit(account, path[1])
        else:
            raise LookupError("not_found")
        self.respond(200, result)

    def admin(self, path, query, origin):
        store = self.server.store
        post = self.command == "POST"
        if post and origin != self.server.origin:
            raise PermissionError("invalid_origin")
        if path == ["login"]:
            if not post:
                self.respond(200, page(
                    '<form method="post"><label>Ключ владельца '
                    '<input name="credential" type="password" required></label> '
                    '<button>Войти</button></form>'))
            elif not self.throttle("login"):
                form = self.body("application/x-www-form-urlencoded")
                token = store.login(form.get("credential", ""), "owner")
                self.redirect("/admin", cookie=session_cookie(token, 3600))
            return
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookies[COOKIE].value if COOKIE in cookies else ""
        if not token and not path and not post:
            self.redirect("/admin/login")
            return
        actor = store.actor(token, "owner")
        if not post and not path:
            status = query.get("status", [""])[0]
            search = query.get("q", [""])[0][:80]
            offset = offset_from(query)
            if status not in STATUSES:
                raise ValueError("invalid_status")
            orders = store.list_orders(status=status, query=search, offset=offset)
            self.respond(200, order_list(orders, status, search, offset, actor["csrf"]))
        elif not post and path[:1] == ["orders"] and len(path) == 2:
            self.respond(200, order_detail(store.detail(path[1]), actor["csrf"]))
        elif post:
            form = self.body("application/x-www-form-urlencoded")
            if not compare_digest(form.get("csrf", "").encode(), actor["csrf"].encode()):
                raise PermissionError("invalid_csrf")
            if self.throttle("write"):
                return
            if path == ["logout"]:
                store.logout(token)
                self.redirect("/admin/login", cookie=session_cookie("", 0))
            elif (path[:1] == ["orders"] and len(path) == 3
                  and path[2] in ("confirm", "reject", "refund")):
                order_id, action = path[1:]
                try:
                    store.review(actor["id"], order_id, action, form.get("reason", ""),
                                 form.get("reference", "").strip(),
                                 int(form["amount_kopeks"]) if "amount_kopeks" in form else None)
                except (Conflict, ValueError):
                    self.respond(409, order_detail(
                        store.detail(order_id), actor["csrf"],
                        "Операция отклонена. Проверьте статус, сумму и уникальность DEMO-номера.",
                    ))
                else:
                    self.redirect(f"/admin/orders/{order_id}")
            else:
                raise LookupError("not_found")
        else:
            raise LookupError("not_found")


def session_cookie(token, max_age):
    return f"{COOKIE}={token}; Path=/admin; HttpOnly; SameSite=Strict; Max-Age={max_age}"


def offset_from(query):
    offset = int(query.get("offset", ["0"])[0])
    if not 0 <= offset <= 100_000:
        raise ValueError("invalid_offset")
    return offset


def page(content):
    return ('<!doctype html><html lang="ru"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Демо-заказы</title><main><h1>Демо-заказы</h1>'
            '<p>Используйте только фиктивные заявки и номера DEMO. Продажи выключены.</p>'
            f'{content}</main></html>')


def csrf_field(csrf):
    return f'<input type="hidden" name="csrf" value="{escape(csrf)}">'


def order_list(orders, status, query, offset, csrf):
    filters = " · ".join(
        f'<a href="/admin?{escape(urlencode({"status": key, "q": query}))}">{label}</a>'
        for key, label in STATUSES.items()
    )
    rows = []
    for order in orders:
        oid = escape(order["order_id"])
        cells = [f'<a href="/admin/orders/{oid}">{oid}</a>',
                 escape(order["account_id"]), str(order["days"]), price(order),
                 escape(order["method"]), timestamp(order["created_at"]),
                 STATUSES[order["status"]]]
        rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    links = []
    for label, start in (("Назад", offset - 50), ("Дальше", offset + 50)):
        if 0 <= start <= 100_000 and (start < offset or len(orders) == 50):
            params = urlencode({"status": status, "q": query, "offset": start})
            links.append(f'<a href="/admin?{escape(params)}">{label}</a>')
    return page(
        f'<form method="post" action="/admin/logout">{csrf_field(csrf)}<button>Выйти</button></form>'
        f'<p>{filters}</p><form method="get" action="/admin">'
        f'<input type="hidden" name="status" value="{escape(status)}">'
        f'<label>ID заказа или аккаунта <input name="q" value="{escape(query)}"></label> '
        '<button>Найти</button></form>'
        f'<h2>{STATUSES[status]}</h2>'
        '<table><thead><tr><th>Заказ</th><th>Аккаунт</th><th>Дни</th><th>Сумма</th>'
        '<th>Способ</th><th>Создан</th><th>Статус</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table><p>{" · ".join(links)}</p>'
    )


def order_detail(order, csrf, notice=""):
    oid = escape(order["order_id"])
    status = order["status"]
    events = "".join(
        f'<li>{timestamp(event["occurred_at"])} · {escape(event["actor"])} · '
        f'{escape(event["action"])} · {escape(event["reason"])}</li>'
        for event in order["events"]
    )
    actions = []
    if status in ("awaiting_payment", "under_review"):
        if order["method"] == "bank_transfer":
            actions.append(("confirm", "Подтвердить демо-перевод",
                            '<label>Номер из фиктивной выписки '
                            '<input name="reference" placeholder="DEMO-1234" required></label> '
                            '<label>Сумма в копейках '
                            '<input type="number" name="amount_kopeks" required></label> '))
        actions.append(("reject", "Отклонить", ""))
    elif status == "confirmed":
        actions.append(("refund", "Записать демо-возврат", ""))
    forms = "".join(
        f'<form method="post" action="/admin/orders/{oid}/{action}">{csrf_field(csrf)}'
        f'{fields}<label>Причина <input name="reason" maxlength="200" required></label> '
        f'<button>{label}</button></form>'
        for action, label, fields in actions
    )
    return page(
        f'<p><a href="/admin">Все заказы</a></p><h2>{oid}</h2>'
        f'<p>{escape(order["account_id"])} · {order["days"]} дн. · {price(order)} · '
        f'{escape(order["method"])} · {timestamp(order["created_at"])}</p>'
        f'<p>{STATUSES[status]} · {escape(order["reference"] or "—")}</p>'
        f'<p role="alert">{escape(notice)}</p>{forms}<h3>Журнал</h3><ul>{events}</ul>'
    )


def price(order):
    rubles, kopeks = divmod(order["amount_kopeks"], 100)
    return f'{rubles},{kopeks:02d} ₽'


def timestamp(value):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    provision = commands.add_parser("provision")
    provision.add_argument("role", choices=("owner", "buyer"))
    provision.add_argument("account_id")
    grant = commands.add_parser("grant-friend")
    grant.add_argument("account_id")
    grant.add_argument("--days", type=int, required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if os.environ.get("SALES_ENABLED", "0") != "0":
        parser.error("The private demo requires SALES_ENABLED=0")
    store = Orders(args.db)
    if args.command == "provision":
        try:
            print(store.provision(args.account_id, args.role))
        except (sqlite3.IntegrityError, ValueError):
            parser.error("Invalid or duplicate account")
    elif args.command == "grant-friend":
        try:
            print(json.dumps(store.grant_friend_access(args.account_id, args.days)))
        except (LookupError, ValueError) as exc:
            parser.error(str(exc))
    else:
        with DemoServer(args.port, store) as server:
            print(f"Private demo running at {server.origin}/admin")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
