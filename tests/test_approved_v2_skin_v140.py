"""The approved six-screen skin keeps real controls and packaged artwork."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def test_approved_design_keeps_original_logo_and_all_artwork_is_packaged():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    ui = ROOT / "ui"
    assert html.index('href="gold_ui.css"') < html.index('href="approved_v2.css"')
    assert html.index('href="skinpay.css"') < html.index('href="approved_v2.css"')
    assert (ui / "pirate_token.png").is_file()
    css = (ui / "approved_v2.css").read_text(encoding="utf-8")
    assert "design-home-art.png" in css
    assert ".design-home-art" in css
    for asset in re.findall(r"url\(['\"]?([^)'\"]+)", css):
        assert not asset.startswith(("http:", "https:", "file:")), asset
        assert (ui / asset).is_file(), asset
    assert "Fortnite Pirate Token" in (ui / "gold_ui.js").read_text(encoding="utf-8")


def test_home_has_real_control_buttons_and_live_status_not_screenshot_controls():
    gold_js = (ROOT / "ui" / "gold_ui.js").read_text(encoding="utf-8")
    app_js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    home = gold_js.split("PAGE.home = function()", 1)[1].split("PAGE.updates", 1)[0]
    for action in ("start", "pause", "stop"):
        assert re.search(r'<button\b[^>]*data-act="' + action + '"', home)
    assert 'data-live="launcher-engine-status"' in home
    assert 'data-live="launcher-game-status"' in home
    assert 'class="design-home-art"' in home
    assert 'class="afk-pause-banner"' in app_js
    assert 'data-live="pause-hint"' not in gold_js
    assert 'data-live="pause-hint"' in app_js
