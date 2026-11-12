"""Local support reports and strictly allowlisted support destinations.

Reports are created only after the user clicks "Create report". Nothing
is uploaded to Telegram, Discord, GitHub or any other service automatically.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# Set the owner's official support contacts before distributing the launcher.
# Never guess addresses or put customer account information in these fields.
TELEGRAM_URL = ""
DISCORD_URL = ""
GITHUB_ISSUES_URL = "https://github.com/9akarena8-bit/easy-rewards/issues/new"

def contacts() -> dict[str, str]:
    return {"github": GITHUB_ISSUES_URL,
            "telegram": TELEGRAM_URL,
            "discord": DISCORD_URL}

def verified_contact(channel: str) -> str | None:
    url = contacts().get(channel, "")
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return None
    domains = {"github": {"github.com"},
               "telegram": {"t.me", "telegram.me"},
               "discord": {"discord.gg", "discord.com"}}
    if parsed.hostname not in domains.get(channel, set()):
        return None
    return url

def clean(value: object) -> str:
    """Keep potentially sensitive credentials and personal paths out of reports."""
    value = str(value)
    value = re.sub(r"(?i)(authorization|api[_-]?key|password|secret|token)(\s*[:=]\s*)\S+",
                   r"\1\2[REDACTED]", value)
    value = re.sub(r"(?i)[a-z]:[\\/](?:users|пользователи)[\\/][^\\/\s]+",
                   r"[USER_DIR]", value)
    return value[:600]

def report_text(version: str, engine, diagnostics: dict, controls: dict,
                log: list[dict]) -> str:
    lines = [
        "Fortnite Pirate Token — support report",
        "Created (local time): " + datetime.now().astimezone().isoformat(timespec="seconds"),
        "Version: " + clean(version),
        "Engine: " + clean(engine.state),
        "Running: " + str(bool(engine.running)),
        "Paused: " + str(bool(engine.paused)),
        "Pause reason: " + clean(getattr(engine, "pause_reason", "")),
        "Runtime (seconds): " + str(round(engine.runtime)),
        "Actions recorded: " + str(engine.input_count),
        "Lobby stage: " + clean(getattr(engine, "lobby_state", "idle")),
        "Lobby clicks: " + str(getattr(engine, "lobby_clicks", 0)),
        "Last lobby button: " + clean(getattr(engine, "lobby_last_button", "")),
        "Replay attempts: " + str(engine.replay_attempts),
        "Replay status: " + clean(engine.replay_status),
        "Last input: " + clean(engine.last_input),
        "Last input error: " + clean(engine.last_input_error),
        "Waiting reason: " + clean(engine.wait_reason),
        "Fortnite window found: " + str(bool(diagnostics.get("game_found"))),
        "Fortnite foreground: " + str(bool(diagnostics.get("game_active"))),
        "Last Python command: " + clean(controls.get("last", "none")),
        "Control sequence: " + str(controls.get("sequence", 0)),
        "Start pending: " + str(bool(controls.get("start_pending", False))),
        "Start phase: " + clean(controls.get("start_phase", "unknown")),
        "Start error: " + clean(controls.get("start_error", "")),
        "",
        "--- Recent application log (newest last) ---",
    ]
    for item in log[-40:]:
        values = item.get("kw") or {}
        fields = ", ".join(clean(k) + "=" + clean(v) for k, v in values.items())
        lines.append(clean(item.get("t", "")) + " " + clean(item.get("key", ""))
                     + (" (" + fields + ")" if fields else ""))
    lines.append("")
    lines.append("Review this report before sharing it. No file is sent automatically.")
    return "\n".join(lines) + "\n"

def save_report(base: Path, text: str) -> Path:
    folder = Path(base) / "support"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = folder / f"report_{stamp}.txt"
    destination.write_text(text, encoding="utf-8")
    return destination
