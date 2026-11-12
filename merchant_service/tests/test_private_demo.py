import concurrent.futures
from http.client import HTTPConnection
import json
from pathlib import Path
import re
import sqlite3
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from merchant_service.orders import Orders
from merchant_service.private_demo import DemoServer


class PrivateDemoTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "demo.sqlite3"
        self.store = Orders(self.path)
        self.owner_key = self.store.provision("owner-demo", "owner")
        self.buyer_key = self.store.provision("buyer-demo", "buyer")
        self.other_key = self.store.provision("other-demo", "buyer")
        self.server = DemoServer(0, self.store)
        worker = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        worker.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(worker.join)
        self.addCleanup(self.server.shutdown)
        self.buyer = self.login_buyer(self.buyer_key)
        self.other = self.login_buyer(self.other_key)

    def request(self, method, path, *, bearer=None, payload=None, form=None, cookie=None, **headers):
        if bearer is not None:
            headers["Authorization"] = f"Bearer {bearer}"
        if cookie is not None:
            headers["Cookie"] = cookie
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload)
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers.setdefault("Origin", self.server.origin)
            body = urlencode(form)
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=8)
        try:
            conn.request(method, path, body, headers)
            response = conn.getresponse()
            raw = response.read().decode("utf-8")
            data = json.loads(raw) if response.headers.get_content_type() == "application/json" else raw
            return response.status, data, response.headers
        finally:
            conn.close()

    def login_buyer(self, credential):
        code, data, _ = self.request("POST", "/api/v1/session", payload={"credential": credential})
        self.assertEqual(code, 200)
        return data["token"]

    def login_owner(self):
        code, _, headers = self.request("POST", "/admin/login", form={"credential": self.owner_key})
        self.assertEqual(code, 303)
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly; SameSite=Strict", cookie)
        return cookie.split(";")[0]

    def create(self, plan="day", method="bank_transfer", request_id="request-1", bearer=None):
        code, order, _ = self.request("POST", "/api/v1/orders", bearer=bearer or self.buyer,
                                      payload={"plan": plan, "method": method, "request_id": request_id})
        self.assertEqual(code, 200)
        return order

    def admin_action(self, cookie, order, action, **fields):
        path = f'/admin/orders/{order["order_id"]}'
        code, page, _ = self.request("GET", path, cookie=cookie)
        self.assertEqual(code, 200)
        # Use the session CSRF token even for replay after the action disappears.
        listing = self.request("GET", "/admin", cookie=cookie)[1]
        csrf = re.search(r'name="csrf" value="([^"]+)"', listing)[1]
        return self.request("POST", f"{path}/{action}", cookie=cookie,
                            form={"csrf": csrf, "reason": "Synthetic statement", **fields})[0]

    def access(self, bearer=None):
        code, data, _ = self.request("GET", "/api/v1/entitlement", bearer=bearer or self.buyer)
        self.assertEqual(code, 200)
        return data

    def test_buyer_owner_roundtrip_all_tariffs_renew_refund_and_restart(self):
        owner = self.login_owner()
        for i, (plan, amount, days) in enumerate(
            (("day", 5900, 1), ("three_days", 12900, 3), ("week", 24900, 7))
        ):
            with self.subTest(plan=plan):
                order = self.create(plan, request_id=f"request-{i}")
                self.assertEqual((order["days"], order["amount_kopeks"], order["currency"]),
                                 (days, amount, "RUB"))
                self.assertEqual(order["status"], "awaiting_payment")
                path = f'/api/v1/orders/{order["order_id"]}'
                self.assertEqual(self.request("GET", path, bearer=self.other)[0], 404)
                self.assertEqual(self.request("POST", path + "/submit", bearer=self.buyer)[1]["status"],
                                 "under_review")
                before = self.access()
                fields = {"reference": f"DEMO-BANK-{i}", "amount_kopeks": amount}
                with concurrent.futures.ThreadPoolExecutor(2) as workers:
                    results = workers.map(lambda _: self.admin_action(owner, order, "confirm", **fields),
                                          range(2))
                    self.assertEqual(list(results), [303, 303])
                self.assertEqual(self.request("GET", path, bearer=self.buyer)[1]["status"], "confirmed")
                after = self.access()
                self.assertTrue(after["active"])
                confirmed_at = self.store.detail(order["order_id"])["confirmed_at"]
                self.assertEqual(after["expires_at"],
                                 max(before["expires_at"] or 0, confirmed_at) + days * 86400)
                self.assertEqual(len(self.store.detail(order["order_id"])["events"]), 1)
        reopened = Orders(self.path)
        self.assertEqual(reopened.entitlement("buyer-demo"), after)
        self.assertFalse(self.access(self.other)["active"])
        self.assertEqual(self.admin_action(owner, order, "refund"), 303)
        self.assertEqual(self.admin_action(owner, order, "refund"), 303)
        self.assertEqual(self.access(), before)
        self.assertEqual([event["action"] for event in reopened.detail(order["order_id"])["events"]],
                         ["payment_confirmed", "payment_refunded"])

    def test_access_control_order_input_and_csrf(self):
        order = self.create()
        self.assertEqual(self.create(), order)
        invalid = {"plan": "week", "method": "bank_transfer", "request_id": "request-1"}
        self.assertEqual(self.request("POST", "/api/v1/orders", bearer=self.buyer, payload=invalid)[0], 409)
        for field, value in (("amount_kopeks", 1), ("account_id", "other-demo"), ("status", "confirmed")):
            self.assertEqual(self.request("POST", "/api/v1/orders", bearer=self.buyer,
                                          payload={**invalid, field: value})[0], 400)
        detail = f'/admin/orders/{order["order_id"]}'
        self.assertEqual(self.request("GET", detail)[0], 403)
        self.assertEqual(self.request("GET", detail, cookie=f"merchant_demo_owner={self.buyer}")[0], 403)
        self.assertEqual(self.request("POST", "/admin/login", form={"credential": self.buyer_key})[0], 403)
        self.assertEqual(self.request("POST", "/api/v1/session",
                                      payload={"credential": self.owner_key})[0], 403)
        owner = self.login_owner()
        self.assertEqual(self.request("POST", detail + "/reject", cookie=owner, form={"csrf": "wrong"})[0],
                         403)
        self.assertEqual(self.request("POST", detail + "/reject", cookie=owner, form={},
                                      Origin="https://other.example")[0], 403)
        self.assertEqual(self.request("GET", "/api/v1/catalog", Host="other.example")[0], 403)
        with patch("merchant_service.orders.time.time", return_value=time.time() + 3601):
            self.assertEqual(self.request("GET", detail, cookie=owner)[0], 403)
            self.assertEqual(self.request("GET", "/api/v1/orders", bearer=self.buyer)[0], 403)
        self.assertEqual(self.store.detail(order["order_id"])["events"], [])

    def test_skin_cannot_activate_and_reference_cannot_pay_twice(self):
        owner = self.login_owner()
        skin = self.create(method="steam_items")
        second, third = (self.create(request_id=f"request-{i}") for i in (2, 3))
        fields = {"reference": "DEMO-BANK-1", "amount_kopeks": 5900}
        self.assertEqual(self.admin_action(owner, skin, "confirm", **fields), 409)
        self.assertEqual(self.admin_action(owner, second, "confirm",
                                           **{**fields, "amount_kopeks": 1}), 409)
        self.assertFalse(self.access()["active"])
        with concurrent.futures.ThreadPoolExecutor(2) as workers:
            results = workers.map(lambda order: self.admin_action(owner, order, "confirm", **fields),
                                  (second, third))
            self.assertEqual(sorted(results), [303, 409])
        self.assertEqual(self.admin_action(owner, skin, "reject"), 303)
        page = self.request("GET", "/admin?status=rejected&q=buyer-demo", cookie=owner)[1]
        self.assertIn(skin["order_id"], page)
        self.assertNotIn(second["order_id"], page)

    def test_rollback_and_unknown_webhook(self):
        owner = self.login_owner()
        order = self.create()
        fields = {"reference": "DEMO-BANK-1", "amount_kopeks": 5900}
        with patch.object(self.store, "_update_entitlement", side_effect=sqlite3.OperationalError):
            self.assertEqual(self.admin_action(owner, order, "confirm", **fields), 503)
        detail = self.store.detail(order["order_id"])
        self.assertEqual(detail["status"], "awaiting_payment")
        self.assertIsNone(detail["reference"])
        self.assertEqual(detail["events"], [])
        self.assertFalse(self.access()["active"])
        self.assertEqual(self.request("POST", "/api/v1/webhook", bearer=self.buyer, payload=fields)[0], 404)
        self.assertEqual(self.admin_action(owner, order, "confirm", **fields), 303)

    def test_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.request("POST", "/api/v1/session", payload={"credential": "bad"})[0], 403)
        self.assertEqual(self.request("POST", "/api/v1/session", payload={"credential": "bad"})[0], 429)
