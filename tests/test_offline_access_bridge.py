"""Check the packaged launcher's offline-license bridge without game input."""
import base64
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import app
from backend import Backend
from merchant_service import offline_license


class OfflineAccessBridgeTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(folder)
        self.data = self.root / "data"
        assets = self.root / "assets"
        assets.mkdir()
        self.key = Ed25519PrivateKey.generate()
        (assets / "license-public.pem").write_bytes(self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.enterContext(patch.object(sys, "_MEIPASS", str(self.root), create=True))
        self.enterContext(patch.object(sys, "frozen", True, create=True))
        self.bridge = Backend(self.data, SimpleNamespace())
        self.addCleanup(self.bridge.shutdown)
        self.now = int(time.time())
        self.expires = self.now + 60
        verify = offline_license.verify_license
        self.enterContext(patch.object(offline_license, "verify_license",
                                        side_effect=lambda *args: verify(*args, now=self.now)))

    def document(self, installation=None):
        payload = {
            "version": 1, "license_id": "A" * 32,
            "installation_id": installation or self.bridge._installation_id,
            "issued_at": self.expires - 60, "expires_at": self.expires, "access": "friend",
        }
        signature = self.key.sign(offline_license.canonical_payload(payload))
        return json.dumps({"payload": payload, "signature": base64.b64encode(signature).decode()})

    def test_import_persists_and_invalid_document_preserves_access(self):
        self.assertTrue(self.bridge.offline_activate(self.document())["active"])
        self.assertFalse(self.bridge.offline_activate(self.document("B" * 32))["ok"])
        reopened = Backend(self.data, SimpleNamespace())
        self.addCleanup(reopened.shutdown)
        self.assertEqual(reopened._offline_status()["installation_id"], self.bridge._installation_id)
        self.assertEqual(reopened._offline_status()["access"], "friend")

    def test_signed_owner_code_is_perpetual_without_administrative_api(self):
        payload = {
            "version": 2, "license_id": "B" * 32,
            "installation_id": self.bridge._installation_id,
            "issued_at": self.now, "expires_at": None, "access": "owner",
        }
        doc = {"payload": payload, "signature": base64.b64encode(
            self.key.sign(offline_license.canonical_payload(payload))).decode()}
        result = self.bridge.offline_activate(offline_license.activation_code(doc))
        self.assertTrue(result["ok"])
        self.assertTrue(result["active"])
        self.assertIsNone(result["expires_at"])
        self.assertEqual(result["access"], "owner")
        self.assertTrue(self.bridge._access_allowed())
        self.assertNotIn("issue_license", self.bridge.API)
        self.assertNotIn("create_admin", self.bridge.API)
        reopened = Backend(self.data, SimpleNamespace())
        self.addCleanup(reopened.shutdown)
        self.assertEqual(reopened._offline_status()["access"], "owner")
        self.assertIsNone(reopened._offline_status()["expires_at"])

    def test_frozen_start_and_resume_require_a_license_even_with_environment_flag(self):
        self.bridge.engine = Mock(running=True, paused=True, stopping=False)
        with patch.dict("os.environ", {"FPT_OWNER_TEST": "1"}):
            self.assertEqual(self.bridge.start()["reason"], "subscription_required")
            self.assertEqual(self.bridge.pause()["reason"], "subscription_required")
        self.bridge.engine.start.assert_not_called()
        self.bridge.engine.toggle_pause.assert_not_called()

    def test_watchdog_stops_on_expiry_without_state_polling(self):
        self.assertTrue(self.bridge.offline_activate(self.document())["ok"])
        stopped = threading.Event()
        self.bridge.engine = Mock(running=True, paused=False, stopping=False)
        self.bridge.engine.stop.side_effect = stopped.set
        self.assertTrue(self.bridge.start()["ok"])
        self.now = self.expires
        self.assertTrue(stopped.wait(2), "expiry must stop the engine without polling the bridge")

    def test_packaged_classic_and_cli_flags_cannot_open_classic(self):
        for flag in ("--classic", "--cli"):
            with self.subTest(flag=flag):
                modern = Mock()
                modern.main.return_value = 0
                classic = Mock()
                with patch.object(sys, "argv", ["EasyRewards.exe", flag]), patch.dict(
                    sys.modules, {"webapp": modern, "app_classic": classic}
                ):
                    self.assertEqual(app.main(), 0)
                modern.main.assert_called_once()
                classic.main.assert_not_called()


if __name__ == "__main__":
    unittest.main()
