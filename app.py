"""Easy Rewards launcher: modern window if pywebview/WebView2 works, otherwise the classic Tk window."""
import sys
from paths import data


def main() -> int:
    if sys.platform != "win32":
        print("Easy Rewards only runs on Windows.")
        return 1
    if "--classic" not in sys.argv and "--cli" not in sys.argv:
        try:
            import webapp
        except ImportError:
            webapp = None  # pywebview missing -> classic window
        if webapp is not None:
            try:
                return webapp.main()
            except Exception:
                import traceback
                from pathlib import Path
                (data() / "crash.log").write_text(traceback.format_exc(), encoding="utf-8")
                print("New window failed (see crash.log), starting the classic window.")
    import app_classic
    return app_classic.main()


if __name__ == "__main__":
    sys.exit(main())
