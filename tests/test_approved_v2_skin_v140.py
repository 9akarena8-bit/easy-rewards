"""Approved v2 CSS/SVG skin must load after gold and SkinPay styles."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_approved_v2_uses_original_logo_and_pirate_ship_scene():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    ui = ROOT / "ui"
    assert html.index('href="gold_ui.css"') < html.index('href="approved_v2.css"')
    assert html.index('href="skinpay.css"') < html.index('href="approved_v2.css"')
    assert (ui / "pirate_token.png").is_file()
    css = (ui / "approved_v2.css").read_text(encoding="utf-8")
    svg = (ui / "pirate_seascape.svg").read_text(encoding="utf-8")
    assert 'url("pirate_seascape.svg")' in css
    assert ".gold-hero" in css
    assert "viewBox=" in svg and "<svg " in svg
    assert "Fortnite Pirate Token" in (ui / "gold_ui.js").read_text(encoding="utf-8")


def test_home_uses_existing_layout_and_afk_keeps_pause_hint_on_own_page():
    gold_js = (ROOT / "ui" / "gold_ui.js").read_text(encoding="utf-8")
    app_js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'class="gold-hero"' in gold_js
    assert 'class="gold-chest"' in gold_js
    assert 'class="afk-pause-banner"' in app_js
    assert 'data-live="pause-hint"' not in gold_js
    assert 'data-live="pause-hint"' in app_js
