"""Integration checks for merged design and anti-AFK release."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_gold_ui_is_loaded_after_core_ui():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    assert 'src="app.js"' in html
    assert 'src="gold_ui.js"' in html
    assert html.index('src="app.js"') < html.index('src="gold_ui.js"')
    assert 'href="gold_ui.css"' in html


def test_native_window_branding_and_original_logo():
    shell = (ROOT / "webapp.py").read_text(encoding="utf-8")
    assert '"Fortnite Pirate Token", UI.as_uri()' in shell
    assert (ROOT / "ui" / "pirate_token.png").exists()
    assert (ROOT / "ui" / "hero_chest.svg").exists()


def test_gold_ui_preserves_original_control_paths():
    source = (ROOT / "ui" / "gold_ui.js").read_text(encoding="utf-8")
    original = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'const originalRender = render;' in source
    assert 'render = renderGold;' in source
    assert 'data-page="afk"' in source
    assert 'data-act="ptest"' in source
    assert 'data-act="start"' in source
    assert 'data-act="stop"' in source
    assert 'function render(' in original
    assert 'data-act="uinst"' in original


def test_no_gold_edition_branding_and_subscription_not_live():
    source = (ROOT / "ui" / "gold_ui.js").read_text(encoding="utf-8")
    assert "GOLD EDITION" not in source
    assert 'const remaining = ()' in source
    assert (ROOT / "subscription_preview.py").exists()
    assert "1.3.9" == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
