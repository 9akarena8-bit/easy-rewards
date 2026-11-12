"""Static, non-invasive checks for an EasyRewards integration candidate.

This is a source/contract presence gate, NOT an E2E test, game compatibility
claim, anti-cheat assessment, or confirmation that real payments work.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

# Each marker is a documented API/safety dependency of the v1.4.3 candidate.
# A source-only gate intentionally catches missing cherry-picks before packaging.
REQUIRED = (
    ("async_update_api", "backend.py", r"\bdef\s+update_check_async\s*\("),
    ("launch_status", "backend.py", r"\b_launch_status\b"),
    ("epic_capability", "backend.py", r"\bepic_launcher_available\b"),
    ("hotkey_cleanup", "webapp.py", r"\bhotkeys\.close\s*\("),
    ("fortnite_window_detection", "winio.py", r"\bgame_window_found\b"),
    ("news_overlay_open", "ui/gold_ui.js", r"data-news-open"),
    ("news_overlay_close", "ui/gold_ui.js", r"data-news-close"),
    ("safe_support_report", "support_report.py", r"\bdef\s+clean\s*\("),
    ("discord_notifications", "discord_notifications.py", r"\b(?:Discord|discord)\b"),
    ("demo_orders_not_payment", "merchant_service/external_orders.py", r"['\"]payment_verified['\"]\s*:\s*False"),
    ("demo_orders_no_licence", "merchant_service/external_orders.py", r"['\"]licence_granted['\"]\s*:\s*False"),
)


def source_sha(root: Path) -> str | None:
    try:
        p = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        sha = p.stdout.strip().lower()
        return sha if re.fullmatch(r"[a-f0-9]{40}", sha) else None
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None



def git_worktree_clean(root: Path) -> bool | None:
    """Reject staged, unstaged, or untracked source changes at release time.

    HEAD alone is not enough: the installer could be built from edited source
    while still claiming the previous Git SHA. Git honors .gitignore.
    """
    try:
        p = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1",
             "--untracked-files=normal"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return not bool(p.stdout.strip())
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def inspect(root: Path, expected_sha: str | None = None) -> dict:
    root = root.resolve()
    results = []
    for check_id, rel, pattern in REQUIRED:
        path = root / rel
        try:
            # Limit the static scan to source files; no secrets are printed.
            content = path.read_text(encoding="utf-8")
            exists = True
            found = bool(re.search(pattern, content))
        except (OSError, UnicodeError):
            exists = False
            found = False
        results.append({"id": check_id, "file": rel, "ok": found,
                        "reason": "found" if found else "missing_contract" if exists else "file_unavailable"})
    sha = source_sha(root)
    expected_sha = expected_sha.lower() if expected_sha else None
    sha_ok = (sha == expected_sha) if expected_sha else None
    if expected_sha:
        results.append({"id": "expected_source_sha", "file": ".git", "ok": sha_ok,
                        "reason": "found" if sha_ok else "sha_mismatch_or_git_unavailable"})
        clean = git_worktree_clean(root)
        results.append({"id": "clean_worktree", "file": ".git", "ok": clean is True,
                        "reason": "clean" if clean is True else
                                  "dirty_worktree" if clean is False else
                                  "git_status_unavailable"})
    return {"source_sha": sha, "expected_source_sha": expected_sha,
            "passed": all(item["ok"] for item in results), "checks": results,
            "limitations": "Static markers only; manually test WebView2, Windows, game, privacy, and demo entitlement."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="Checked-out candidate root")
    parser.add_argument("--expected-sha", help="40-char exact source SHA used by the installer")
    parser.add_argument("--json", action="store_true", help="Print JSON (no secrets)")
    args = parser.parse_args(argv)
    if args.expected_sha and not re.fullmatch(r"[a-fA-F0-9]{40}", args.expected_sha):
        parser.error("--expected-sha requires exactly 40 hex characters")
    result = inspect(Path(args.root), args.expected_sha)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["checks"]:
            print(f"{'PASS' if item['ok'] else 'FAIL'} {item['id']} ({item['file']}): {item['reason']}")
        print("STATIC PREFLIGHT " + ("PASS" if result["passed"] else "FAIL"))
        print("Note: Windows/WebView2/manual input and payments remain unverified.")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
