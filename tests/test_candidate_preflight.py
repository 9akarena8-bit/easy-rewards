"""Independent release audit tests; never call live Fortnite or payment APIs."""
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parents[1] / "scripts" / "candidate_preflight.py"
spec = importlib.util.spec_from_file_location("candidate_preflight", HERE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fill_fake_candidate(root: Path):
    for check_id, rel, _ in module.REQUIRED:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        markers = {
            "async_update_api": "def update_check_async(self):",
            "launch_status": "self._launch_status = 'idle'",
            "epic_capability": "epic_launcher_available = True",
            "hotkey_cleanup": "hotkeys.close()",
            "fortnite_window_detection": "game_window_found",
            "news_overlay_open": "data-news-open",
            "news_overlay_close": "data-news-close",
            "safe_support_report": "def clean(value):",
            "discord_notifications": "Discord",
            "demo_orders_not_payment": "'payment_verified': False",
            "demo_orders_no_licence": "'licence_granted': False",
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(markers[check_id] + "\n")


def test_complete_source_passes_presence_check(tmp_path):
    fill_fake_candidate(tmp_path)
    result = module.inspect(tmp_path)
    assert result["passed"]
    assert all(x["ok"] for x in result["checks"])


def test_detects_missing_backend_methods_and_hotkey_cleanup(tmp_path):
    fill_fake_candidate(tmp_path)
    (tmp_path / "backend.py").write_text("# stale integration snapshot\n", encoding="utf-8")
    (tmp_path / "webapp.py").write_text("HotkeyPoller(lambda: None).start()", encoding="utf-8")
    result = module.inspect(tmp_path)
    missing = {x["id"] for x in result["checks"] if not x["ok"]}
    assert {"async_update_api", "launch_status", "epic_capability", "hotkey_cleanup"} <= missing
    assert not result["passed"]


def test_requires_exact_sha_when_supplied(tmp_path):
    fill_fake_candidate(tmp_path)
    result = module.inspect(tmp_path, "f" * 40)
    assert not result["passed"]
    assert result["checks"][-1]["id"] == "expected_source_sha"
    assert not result["checks"][-1]["ok"]


def test_missing_file_is_reported_without_exception(tmp_path):
    result = module.inspect(tmp_path)
    assert not result["passed"]
    assert all(x["reason"] == "file_unavailable" for x in result["checks"])



def test_expected_sha_is_not_enough_when_source_tree_is_dirty(tmp_path, monkeypatch):
    fill_fake_candidate(tmp_path)
    expected = "a" * 40
    monkeypatch.setattr(module, "source_sha", lambda root: expected)
    monkeypatch.setattr(module, "git_worktree_clean", lambda root: False)

    result = module.inspect(tmp_path, expected)
    assert not result["passed"]
    assert result["checks"][-2]["id"] == "expected_source_sha"
    assert result["checks"][-2]["ok"]
    assert result["checks"][-1] == {
        "id": "clean_worktree",
        "file": ".git",
        "ok": False,
        "reason": "dirty_worktree",
    }


def test_attested_clean_tree_passes_when_contracts_exist(tmp_path, monkeypatch):
    fill_fake_candidate(tmp_path)
    expected = "a" * 40
    monkeypatch.setattr(module, "source_sha", lambda root: expected)
    monkeypatch.setattr(module, "git_worktree_clean", lambda root: True)
    assert module.inspect(tmp_path, expected)["passed"]


def test_git_unavailable_never_passes_sha_attestation(tmp_path, monkeypatch):
    fill_fake_candidate(tmp_path)
    expected = "b" * 40
    monkeypatch.setattr(module, "source_sha", lambda root: expected)
    monkeypatch.setattr(module, "git_worktree_clean", lambda root: None)

    checks = module.inspect(tmp_path, expected)["checks"]
    assert checks[-1]["id"] == "clean_worktree"
    assert checks[-1]["reason"] == "git_status_unavailable"
    assert not checks[-1]["ok"]



def test_cli_exit_codes(tmp_path, capsys):
    assert module.main([str(tmp_path)]) == 1
    fill_fake_candidate(tmp_path)
    assert module.main([str(tmp_path), "--json"]) == 0
    assert '"passed": true' in capsys.readouterr().out
