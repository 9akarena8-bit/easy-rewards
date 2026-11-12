"""News reader must show only genuine release notes in a centered accessible modal."""
from pathlib import Path
import json
import release_updater

ROOT = Path(__file__).resolve().parents[1]


def test_news_dialog_has_correct_interactions():
    js = (ROOT / "ui" / "gold_ui.js").read_text(encoding="utf-8")
    css = (ROOT / "ui" / "gold_ui.css").read_text(encoding="utf-8")
    assert 'data-news-open=' in js
    assert 'data-news-close="1"' in js
    assert 'aria-modal="true"' in js
    assert 'ev.key === "Escape"' in js
    assert 'ev.target === patchOverlay' in js
    assert 'gold-patch-is-open' in js
    assert 'const patchNotesHtml' in js
    assert '.gold-patch-overlay' in css
    assert 'backdrop-filter:blur(5px)' in css
    assert 'overscroll-behavior:contain' in css
    assert 'prefers-reduced-motion' in css


def test_no_fake_release_or_old_truncated_notes():
    js = (ROOT / "ui" / "gold_ui.js").read_text(encoding="utf-8")
    assert 'В разработке' not in js[js.index('const newsItems ='):js.index('const subCard =')]
    assert 'Точки интереса' not in js
    assert 'slice(0, full ? 6 : 3)' not in js
    assert 'const all = newsItems()' in js


def test_official_news_includes_beta_full_body_and_actual_date(monkeypatch):
    notes = "Что изменилось\n" + ("Исправление окна Fortnite. " * 70)
    docs = [
        {"tag_name": "v1.4.2", "body": notes, "draft": False,
         "prerelease": True, "published_at": "2026-11-12T03:35:44Z"},
        {"tag_name": "v1.4.0", "body": "Beta 1.4.0", "prerelease": True},
        {"tag_name": "v1.3.9", "body": "Stable"},
        {"tag_name": "v1.5.0", "draft": True, "body": "do not show"},
    ]
    monkeypatch.setattr(release_updater, "_read_limited",
                        lambda url, limit: json.dumps(docs).encode("utf-8"))
    items = release_updater.release_news()
    assert [item["version"] for item in items] == ["1.4.2", "1.4.0", "1.3.9"]
    assert items[0]["prerelease"] is True
    assert items[0]["published_at"] == "2026-11-12T03:35:44Z"
    assert items[0]["notes"] == notes
