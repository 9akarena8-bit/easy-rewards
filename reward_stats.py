"""Thread-safe persistent total of visually detected reward popups (best-effort)."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path


class RewardStats:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.total = 0
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.total = max(0, int(data.get("total", 0)))
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def increment(self) -> None:
        with self._lock:
            self.total += 1
            tmp = self.path.with_name(self.path.name + ".tmp")
            try:
                tmp.write_text(json.dumps({"total": self.total}, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, self.path)
            except OSError:
                # In-memory counter stays valid even if the disk is temporarily unavailable.
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
