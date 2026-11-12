"""License API client for use by the Windows desktop application.

IMPORTANT: This is not yet wired into EasyRewards Backend / Engine / hotkeys.
A local license check alone is not tamper-proof DRM. Never trust a UI-only gate.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit


class LicenseClient:
    def __init__(self, https_server_url: str, storage_path: Path | None = None):
        self.server = https_server_url.rstrip("/")
        parsed = urlsplit(self.server)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Для проверки лицензий необходим HTTPS адрес сервера")
        default_folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "FortnitePirateToken"
        self.storage = Path(storage_path) if storage_path else default_folder / "license.json"

    def _read_local(self) -> dict:
        try:
            data = json.loads(self.storage.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("device_id"), str):
                return data
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        return {"device_id": secrets.token_urlsafe(24)}

    def _remote(self, key: str, device_id: str, action="check") -> dict:
        payload = json.dumps({"key": key, "device_id": device_id}).encode("utf-8")
        req = request.Request(self.server + "/v1/" + action, data=payload,
                              headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=8) as result:
                return json.load(result)
        except HTTPError as ex:
            try:
                return json.loads(ex.read())
            except (ValueError, OSError):
                return {"ok": False, "error": "server_rejected"}
        except (URLError, TimeoutError, OSError, ValueError):
            # Fail closed by default. Production may implement carefully bounded grace.
            return {"ok": False, "error": "server_unavailable"}

    def activate(self, key: str) -> dict:
        local = self._read_local()
        response = self._remote(key.strip(), local["device_id"], "activate")
        if response.get("ok"):
            local["key"] = key.strip()
            self.storage.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.storage.with_suffix(".tmp")
            tmp.write_text(json.dumps(local), encoding="utf-8")
            tmp.replace(self.storage)
        return response

    def check(self) -> dict:
        local = self._read_local()
        if not local.get("key"):
            return {"ok": False, "error": "not_activated"}
        return self._remote(local["key"], local["device_id"])