# Fortnite Pirate Token v1.4.0 — private beta test

This is an **unofficial** community utility, not affiliated with Epic Games or Fortnite.

## Beta scope
- Original F-token logo and dark gold launcher UI, with restrained translucent cards.
- **Start** attempts to dispatch the Epic Games Launcher protocol if Fortnite is not running.
  Protocol dispatch is only a request; it does not guarantee the game opened or became ready.
- With an existing Fortnite window, Start requests window focus. Windows may deny the request.
- Anti-AFK global Start/Stop hotkeys can be edited in **Settings** and **Anti-AFK**.
  Defaults: F7 Start, F8 Stop. **F12 always stops** the anti-AFK engine,
  independently of custom shortcuts. F6 test, F9 counter, F10 pause are reserved.
- The Stop button and the configured global Stop key must remain responsive.
- All payment methods are *preview-only*. Do not pay, trade skins, or send money to testers.
- Subscriptions are *not* active; there is no reliable licence enforcement or automatic delivery.

## Friends test sequence (Windows 10/11)
1. Download the **Beta Windows Installer** artifact from the project's GitHub Actions beta workflow.
2. Install on a computer where Epic Games Launcher and Fortnite are already installed.
3. Open the app; verify the F-token artwork, home page, gold cards and subscription preview.
4. Under **Settings**, choose distinct function keys, e.g. F3 Start, F4 Stop, F5 Pause/Resume.
   Avoid binding keys that you personally use in a game.
5. With Fortnite closed, press Start; confirm that the Epic Launcher *tries* to open Fortnite.
   If not, note whether the Epic Launcher is installed, and copy the error text.
6. With Fortnite open, check that Start focuses the verified game or displays waiting state.
7. Press the configured Stop key with the launcher minimized. Confirm engine status is Stopped. Restart and press F12: emergency Stop must work even after rebinding.
8. Open Fortnite, press Start, and Alt+Tab to any other window. The engine must
   enter **Paused / focus_lost** without bringing Fortnite back by itself.
   Return to Fortnite. Nothing must resume until **F5** (or F10 / Start shortcut)
   is pressed while Fortnite has focus.
9. Try the Pause button in the launcher while the game is not foreground: a
   clear "return to Fortnite" message must appear, and no input is sent to the
   launcher or other applications. Test F12 during the pause.
10. Disable the "Auto-pause on Alt+Tab" setting and verify input remains
    blocked outside Fortnite and Fortnite focus is not stolen. Re-enable it.
11. Repeat with Start/Stop buttons in the app. Try the custom Pause/Resume key and F10 fallback.
12. Verify that settings are kept after closing and reopening the app.
13. On the Anti-AFK page, click **Отчёт для тестирования**. The launcher opens
    Support and prepares a local text report for review and copying.
14. Report Windows version, app version, reproduction steps, screenshot, and diagnostics
    with personal details/credentials removed. No diagnostics are uploaded automatically.

## Important limitations
- Fortnite and Epic Games do **not** approve third-party gameplay automation. Using this
  software can put an account at risk. No anti-cheat bypass or ban protection is provided.
  Do not test automated actions on an account you cannot afford to lose.
- Never claim an item, currency or reward was earned until the game visibly confirms it.
- The screenshot/template engine can require manual calibration and may not enter or
  replay a match automatically on every display, resolution, language or game update.
- For troubleshooting, use the app's **F6 input test**. It is only a diagnostic and does
  not prove that protected games accept the input.
- Beta installation is not a store product and carries no purchase entitlement.

## Release gate
The beta must pass automated tests and two independent Windows acceptance tests before
any stable release. A real paid launch additionally requires a merchant backend, provider
approval, server-side payment verification, server-side licences, refund terms and data
handling policies. Do not put payment API secrets in this public repository.
