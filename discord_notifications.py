"""Opt-in Discord Webhook notifications.

The webhook URL is a credential stored in the user's local data folder.
It is NEVER returned to the JS frontend, added to diagnostics, or logged.
All network calls happen in a daemon worker, never in the engine/control path.
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

_WEBHOOK_PATH = re.compile(r"/api/webhooks/[0-9]{10,25}/[A-Za-z0-9_-]{20,200}/?")
_MESSAGES = {
    "log.started": "🟢 Fortnite Pirate Token: Anti-AFK started",
    "log.stopped": "🔴 Fortnite Pirate Token: Anti-AFK stopped",
    "log.paused": "⏸️ Fortnite Pirate Token: Anti-AFK paused",
    "log.resumed": "▶️ Fortnite Pirate Token: Anti-AFK resumed",
    "log.replay_clicked": "🔁 Fortnite Pirate Token: Play Again pressed",
    "log.error": "⚠️ Fortnite Pirate Token: application error (check the local log)",
}
_ALLOWED_KEYS = frozenset(_MESSAGES)


def valid_webhook(value: str) -> bool:
    if not isinstance(value, str) or len(value) > 400:
        return False
    try:
        p = urlparse(value)
        return (p.scheme == "https"
                and p.hostname in {"discord.com", "discordapp.com"}
                and p.port in (None, 443)
                and p.username is None and p.password is None
                and not p.params and not p.query and not p.fragment
                and bool(_WEBHOOK_PATH.fullmatch(p.path)))
    except ValueError:
        return False


class DiscordNotifications:
    """One bounded queue. Never blocks the GUI, engine or global hotkey thread."""

    def __init__(self, config_path: Path):
        self.path = Path(config_path)
        self._lock = threading.RLock()
        self._url = ""
        self._enabled = False
        self._last_error = ""
        self._last_sent = ""
        self._last_event_at: dict[str, float] = {}
        self._pending: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=64)
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            candidate = saved.get("webhook_url", "")
            if valid_webhook(candidate):
                self._url = candidate
                self._enabled = saved.get("enabled") is True
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        threading.Thread(target=self._loop, name="discord-notifications",
                         daemon=True).start()

    def status(self) -> dict:
        with self._lock:
            return {
                "enabled": self._enabled,
                "configured": bool(self._url),
                "last_sent": self._last_sent,
                "last_error": self._last_error,
            }

    def configure(self, url: str = "", enabled: bool = False) -> dict:
        """Blank URL keeps the old one. Never echo secrets back to the user."""
        if not isinstance(enabled, bool):
            return {"ok": False, "error": "Invalid enabled flag"}
        if url and not valid_webhook(url):
            return {"ok": False, "error": "Invalid Discord Webhook URL"}
        with self._lock:
            candidate = url or self._url
            if enabled and not candidate:
                return {"ok": False, "error": "Enter a Discord Webhook URL first"}
            # Atomic save: failed writes must preserve the last good settings.
            temporary = self.path.with_name(
                f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
            )
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_text(json.dumps({
                    "webhook_url": candidate,
                    "enabled": enabled,
                }), encoding="utf-8")
                os.replace(temporary, self.path)
            except OSError:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                return {"ok": False, "error": "Cannot save local Discord settings"}
            self._url = candidate
            self._enabled = enabled
        return {"ok": True, **self.status()}

    def clear(self) -> dict:
        with self._lock:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                # The secret remains on disk; do not claim we disconnected.
                return {"ok": False, "error": "Cannot remove local Discord settings"}
            self._url = ""
            self._enabled = False
            self._last_error = ""
        return {"ok": True, **self.status()}

    def notify(self, key: str, *, test: bool = False, runtime_seconds: int | None = None) -> bool:
        if key not in _ALLOWED_KEYS and not test:
            return False
        with self._lock:
            if not self._enabled or not self._url:
                return False
            now = time.monotonic()
            # Avoid notification floods if an error occurs repeatedly.
            minimum = 60 if key == "log.error" else 2
            if not test and now - self._last_event_at.get(key, float("-inf")) < minimum:
                return False
            self._last_event_at[key] = now
            message = ("✅ Fortnite Pirate Token: Discord test notification"
                       if test else _MESSAGES[key])
            if key == "log.stopped" and runtime_seconds is not None and not test:
                seconds = max(0, min(int(runtime_seconds), 30 * 86400))
                duration = f"{seconds // 3600:02d}:{(seconds // 60) % 60:02d}:{seconds % 60:02d}"
                message += f" · session {duration}"
            try:
                self._pending.put_nowait((self._url, message))
                return True
            except queue.Full:
                self._last_error = "Notification queue is full"
                return False

    def _loop(self) -> None:
        while True:
            url, message = self._pending.get()
            try:
                # Disabling/replacing a Webhook invalidates unsent queue items.
                with self._lock:
                    if not self._enabled or self._url != url:
                        continue
                request = Request(
                    url,
                    data=json.dumps({"content": message,
                                     "allowed_mentions": {"parse": []}}).encode("utf-8"),
                    headers={"Content-Type": "application/json",
                             "User-Agent": "FortnitePirateToken/1.3.8"},
                    method="POST",
                )
                # A webhook can be deleted between enqueuing and sending.
                # Never include the webhook URL in the error state.
                with urlopen(request, timeout=8) as response:
                    response.read(1024)
                with self._lock:
                    self._last_error = ""
                    self._last_sent = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except HTTPError as exc:
                with self._lock:
                    self._last_error = "Discord HTTP " + str(exc.code)
            except Exception:
                with self._lock:
                    self._last_error = "Discord connection failed"
            finally:
                self._pending.task_done()
