import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "s.db", "test" * 15)

    def tearDown(self):
        self.tmp.cleanup()

    def paid(self, buyer=123, plan="day", price=50, charge="charge-1"):
        payload = self.store.create_invoice(buyer, plan, price)
        self.assertTrue(self.store.invoice_valid(payload, buyer, "XTR", price))
        return payload, self.store.apply_payment(payload, buyer, "XTR", price, charge)

    def test_invoice_and_payment_validate_user_amount_currency(self):
        payload = self.store.create_invoice(123, "day", 50)
        for buyer, currency, amount in [(124, "XTR", 50), (123, "RUB", 50), (123, "XTR", 51)]:
            self.assertFalse(self.store.invoice_valid(payload, buyer, currency, amount))
            with self.assertRaises(ValueError):
                self.store.apply_payment(payload, buyer, currency, amount, "bad")
        key, expiry, new = self.store.apply_payment(payload, 123, "XTR", 50, "charge-1")
        self.assertTrue(new)
        self.assertTrue(key.startswith("FPT-"))
        self.assertTrue(expiry > 0)

    def test_payment_idempotency_and_renewal(self):
        payload, (key, expires, fresh) = self.paid()
        same_key, same_exp, again = self.store.apply_payment(payload, 123, "XTR", 50, "charge-1")
        self.assertEqual((key, expires, fresh), (same_key, same_exp, True))
        self.assertFalse(again)
        payload2, (key2, expires2, fresh2) = self.paid(plan="week", price=100, charge="charge-2")
        self.assertEqual(key, key2)
        self.assertEqual(expires2, expires + 7 * 86400)
        self.assertTrue(fresh2)
        self.assertFalse(self.store.invoice_valid(payload, 123, "XTR", 50))
        with self.assertRaises(ValueError):
            self.store.apply_payment(payload, 123, "XTR", 50, "different-charge")

    def test_binding_and_reset(self):
        _, (key, _, _) = self.paid()
        device1 = "abc12345678901234567890"
        device2 = "def12345678901234567890"
        self.assertTrue(self.store.validate(key, device1)["ok"])
        self.assertTrue(self.store.validate(key, device1)["ok"])
        self.assertEqual(self.store.validate(key, device2)["error"], "another_device")
        wrong_suffix = '1' if key.endswith('0') else '0'
        self.assertFalse(self.store.validate(key[:-1] + wrong_suffix, device1)["ok"])
        self.assertTrue(self.store.reset_device(123))
        self.assertTrue(self.store.validate(key, device2)["ok"])

    def test_download_one_time(self):
        self.assertIsNone(self.store.create_download(123))
        self.paid()
        token = self.store.create_download(123)
        self.assertTrue(self.store.consume_download(token))
        self.assertFalse(self.store.consume_download(token))

    def test_refund_reduces_time(self):
        self.paid()
        _, (key, expires, _) = self.paid(plan="week", price=100, charge="charge-2")
        self.assertTrue(self.store.record_refund("charge-2"))
        status = self.store.user_status(123)
        self.assertEqual(status["expires_at"], expires - 7 * 86400)
        self.assertFalse(self.store.record_refund("charge-2"))
        self.assertTrue(self.store.validate(key, "abc12345678901234567890")["ok"])

    def test_expired(self):
        self.paid()
        data = self.store.user_status(123)
        with self.store.connection() as db:
            db.execute("UPDATE users SET expires_at=0 WHERE tg_id=123")
        self.assertEqual(self.store.validate(data["key"], "abc12345678901234567890")["error"], "expired")

    def test_expired_invoice_precheckout(self):
        payload = self.store.create_invoice(123, "day", 50)
        with self.store.connection() as db:
            db.execute("UPDATE invoices SET created_at=0 WHERE payload=?", (payload,))
        self.assertFalse(self.store.invoice_valid(payload, 123, "XTR", 50))


if __name__ == "__main__":
    unittest.main()

class BotFlowTests(unittest.TestCase):
    def test_accept_terms_precheckout_and_successful_payment(self):
        import os
        from dataclasses import replace
        from service import Settings, TelegramShop

        class FakeTelegram:
            def __init__(self):
                self.actions = []

            def call(self, method, args=None, timeout=35):
                self.actions.append((method, args))
                return True

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            installer = path / "sample.exe"
            installer.write_bytes(b"installer")
            settings = Settings("test_token", "x" * 40, 999, "https://example.org", "127.0.0.1", 8765,
                                path / "db.sqlite", installer,
                                {"day": 10, "three_days": 0, "week": 0, "month": 0},
                                "support", "https://example.org/terms", "v1", True, False)
            store = Store(settings.database_path, settings.license_secret)
            api = FakeTelegram()
            bot = TelegramShop(settings, store, api)
            message = lambda content: {"message": {"chat": {"type": "private", "id": 101},
                                                  "from": {"id": 101}, **content}}
            callback = lambda data: {"callback_query": {"id": "query1", "from": {"id": 101},
                                                         "message": {"chat": {"type": "private", "id": 101}},
                                                         "data": data}}
            bot.handle_update(message({"text": "/start"}))
            bot.handle_update(callback("buy:day"))
            self.assertFalse(any(a[0] == "sendInvoice" for a in api.actions))
            bot.handle_update(callback("accept:day"))
            invoices = [a[1] for a in api.actions if a[0] == "sendInvoice"]
            self.assertEqual(len(invoices), 1)
            payload = invoices[0]["payload"]
            self.assertEqual(invoices[0]["currency"], "XTR")
            self.assertEqual(invoices[0]["prices"][0]["amount"], 10)
            bot.handle_update({"pre_checkout_query": {"id": "pre1", "from": {"id": 101},
                                                      "invoice_payload": payload, "currency": "XTR", "total_amount": 10}})
            self.assertTrue(api.actions[-1][1]["ok"])
            bot.handle_update(message({"successful_payment": {"invoice_payload": payload, "currency": "XTR",
                                                                    "total_amount": 10,
                                                                    "telegram_payment_charge_id": "paid1"}}))
            expires = store.user_status(101)["expires_at"]
            self.assertTrue(expires > 0)
            bot.handle_update(message({"successful_payment": {"invoice_payload": payload, "currency": "XTR",
                                                                    "total_amount": 10,
                                                                    "telegram_payment_charge_id": "paid1"}}))
            self.assertEqual(expires, store.user_status(101)["expires_at"])