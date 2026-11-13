from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import tempfile
import unittest

from merchant_service.offline_license import verify_license
from merchant_service.owner_license import initialize_keys, issue_license, save_license


class OfflineLicenseTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.password = b"synthetic-test-password"
        self.public_path = initialize_keys(self.directory, self.password)
        self.public = self.public_path.read_bytes()
        self.installation = "1" * 32
        self.now = 1_800_000_000

    def issue(self, reference="friend-01", **overrides):
        options = {"directory": self.directory, "installation_id": self.installation,
                   "days": 7, "method": "friend", "reference": reference,
                   "password": self.password, "now": self.now}
        return issue_license(**{**options, **overrides})

    def verify(self, document, **overrides):
        options = {"public_key_pem": self.public, "installation_id": self.installation,
                   "now": self.now}
        return verify_license(document, **{**options, **overrides})

    def test_friend_access_and_idempotent_file_output(self):
        document = self.issue()
        claims = self.verify(document)
        self.assertEqual(claims["access"], "friend")
        self.assertEqual(claims["expires_at"], self.now + 7 * 86400)
        self.assertEqual(self.issue(now=self.now + 10 * 86400), document)
        output = self.directory / "friend.json"
        save_license(output, document)
        save_license(output, document)
        with self.assertRaises(ValueError):
            save_license(output, self.issue("friend-02"))
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), document)
        self.assertIn(b"BEGIN ENCRYPTED PRIVATE KEY",
                      (self.directory / "private-key.pem").read_bytes())
        with self.assertRaises(ValueError):
            initialize_keys(self.directory, self.password)

    def test_rejects_modified_claims_signature_wrong_installation_and_key(self):
        original = self.issue()
        for name, value in (("expires_at", self.now + 90 * 86400),
                            ("installation_id", "2" * 32), ("access", "paid")):
            with self.subTest(claim=name):
                modified = copy.deepcopy(original)
                modified["payload"][name] = value
                with self.assertRaises(ValueError):
                    self.verify(modified, installation_id=modified["payload"]["installation_id"])
        with self.assertRaises(ValueError):
            self.verify({**original, "signature": "AAAA"})
        with self.assertRaises(ValueError):
            self.verify(original, installation_id="2" * 32)
        other_public = initialize_keys(self.directory / "other", self.password).read_bytes()
        with self.assertRaises(ValueError):
            self.verify(original, public_key_pem=other_public)
        with self.assertRaises(ValueError):
            self.issue("friend-02", password=b"wrong-password")

    def test_expiration_boundary_and_future_issue_time(self):
        document = self.issue()
        expiry = document["payload"]["expires_at"]
        self.verify(document, now=expiry - 1)
        with self.assertRaisesRegex(ValueError, "license_expired"):
            self.verify(document, now=expiry)
        with self.assertRaisesRegex(ValueError, "license_not_yet_valid"):
            self.verify(document, now=self.now - 301)

    def test_manual_payment_issue_and_reference_replay(self):
        options = {"method": "bank_transfer", "days": 3}
        with self.assertRaises(ValueError):
            self.issue("bank-1001", **options)
        with self.assertRaises(ValueError):
            self.issue("bank-1001", **{**options, "days": 2}, reconciled=True)
        with ThreadPoolExecutor(max_workers=2) as workers:
            docs = list(workers.map(
                lambda _: self.issue("bank-1001", **options, reconciled=True), range(2),
            ))
        self.assertEqual(docs[0], docs[1])
        self.assertEqual(self.verify(docs[0])["access"], "paid")
        self.assertEqual(docs[0]["payload"]["expires_at"], self.now + 3 * 86400)
        with self.assertRaises(ValueError):
            self.issue("bank-1001", **options, reconciled=True, installation_id="2" * 32)
        renewed = self.issue("steam-1002", method="steam_items", days=1, reconciled=True)
        self.assertEqual(renewed["payload"]["expires_at"], self.now + 4 * 86400)
