"""Owner/friend lifetime access, manual payment gates, and portable codes."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest

from merchant_service.offline_license import activation_code, parse_license_input, verify_license
from merchant_service.owner_license import initialize_keys, issue_license
from owner_access import validate_request


class PerpetualAccessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.public = initialize_keys(self.directory, b"a-not-real-owner-test-secret").read_bytes()
        self.id = "a" * 32
        self.now = 1_800_000_000

    def issue(self, method, days, ref):
        return issue_license(self.directory, self.id, days, method, ref,
                             password=b"a-not-real-owner-test-secret", now=self.now)

    def test_owner_license_is_perpetual_and_not_admin_key(self):
        doc = self.issue("owner", None, "owner-0001")
        self.assertEqual(doc["payload"]["version"], 2)
        self.assertEqual(doc["payload"]["access"], "owner")
        self.assertIsNone(doc["payload"]["expires_at"])
        self.assertEqual(doc, self.issue("owner", None, "owner-0001"))
        self.assertEqual(verify_license(doc, self.public, self.id, now=2_500_000_000)["access"], "owner")
        with self.assertRaises(ValueError):
            self.issue("owner", 7, "bad-owner")
        with self.assertRaises(ValueError):
            self.issue("owner", 7, "owner-0001")

    def test_friend_code_is_perpetual_signed_and_device_bound(self):
        doc = self.issue("friend", None, "friend-0001")
        code = activation_code(doc)
        self.assertTrue(code.startswith("FPT2."))
        self.assertEqual(parse_license_input(code), doc)
        self.assertEqual(parse_license_input(json.dumps(doc)), doc)
        self.assertEqual(verify_license(parse_license_input(code), self.public, self.id,
                                        now=2_500_000_000)["access"], "friend")
        with self.assertRaisesRegex(ValueError, "other_installation"):
            verify_license(doc, self.public, "b" * 32, now=self.now)
        mutated = copy.deepcopy(doc)
        mutated["payload"]["access"] = "paid"
        with self.assertRaises(ValueError):
            verify_license(mutated, self.public, self.id, now=self.now)
        for bad in ("FPT2.!", "FPT2." + "z" * 103, "wrong license"):
            with self.subTest(bad=bad[:15]), self.assertRaises(ValueError):
                parse_license_input(bad)

    def test_parser_rejects_scalar_and_deeply_nested_documents(self):
        for text in ("null", "[]", '"text"', "[" * 1500 + "]" * 1500):
            with self.subTest(text=text[:12]), self.assertRaisesRegex(ValueError, "invalid_license_document"):
                parse_license_input(text)
        nested = b"[" * 1500 + b"]" * 1500
        code = "FPT2." + base64.urlsafe_b64encode(nested).decode("ascii").rstrip("=")
        with self.assertRaisesRegex(ValueError, "invalid_license_document"):
            parse_license_input(code)

    def test_paid_licenses_always_expire_and_require_manual_verification(self):
        for method in ("bank_transfer", "steam_items"):
            with self.subTest(method=method):
                with self.assertRaises(ValueError):
                    self.issue(method, None, f"{method}-none")
                with self.assertRaises(ValueError):
                    self.issue(method, 365, f"{method}-365")
                with self.assertRaises(ValueError):
                    self.issue(method, 3, f"{method}-unverified")
                with self.assertRaises(ValueError):
                    issue_license(self.directory, self.id, 3, method, f"{method}-unverified",
                                  password=b"a-not-real-owner-test-secret", reconciled="false",
                                  now=self.now)
                doc = issue_license(self.directory, self.id, 3, method, f"{method}-good",
                                    password=b"a-not-real-owner-test-secret", reconciled=True,
                                    now=self.now)
                self.assertEqual(doc["payload"]["access"], "paid")
                self.assertEqual(doc["payload"]["version"], 1)
                with self.assertRaisesRegex(ValueError, "license_expired"):
                    verify_license(doc, self.public, self.id, now=doc["payload"]["expires_at"])
                forged = copy.deepcopy(doc)
                forged["payload"].update(version=2, expires_at=None)
                with self.assertRaises(ValueError):
                    verify_license(forged, self.public, self.id, now=self.now)

    def test_owner_gui_validation(self):
        self.assertEqual(validate_request(self.id, "Бессрочно", "Бессрочно — только владелец", False),
                         (self.id, None, "owner"))
        self.assertEqual(validate_request(self.id, "Бессрочно", "Бесплатно — друг", False),
                         (self.id, None, "friend"))
        with self.assertRaises(ValueError):
            validate_request(self.id, "Бессрочно", "Банковский перевод (ручная проверка)", True)
        with self.assertRaises(ValueError):
            validate_request(self.id, "3", "Предметы Steam (ручная проверка)", False)


if __name__ == '__main__':
    unittest.main()
