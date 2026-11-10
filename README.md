# Easy Rewards

A soft-looking Windows panel that watches the screen with OpenCV template matching, clicks the buttons
you teach it (start next match, continue, claim all, back to lobby) and sends random W/A/S/D holds
(anti-AFK) while no known button is visible.

- Interface languages: **Русский / English / Українська** (switch in the sidebar, applies instantly)
- **Light and dark** themes (sidebar), both soft pastel
- Hotkeys: **F7** start, **F8** stop, **F10** pause / resume

## How to run (Windows)
1. Unzip the folder anywhere (not inside the zip viewer).
2. **Double-click `run.bat`.** It finds Python 3.10+, creates a private environment, installs what is
   needed (first start takes a minute or two) and opens the app. Later starts are instant.
   - "Python was not found": install it from https://www.python.org/downloads/windows/ - tick
     **Add python.exe to PATH** and keep **tcl/tk** ticked - then double-click `run.bat` again.
   - If the app closes with an error, the window stays open and the details are saved in `crash.log`.
3. Optional: `run.bat --cli` runs without a window (F7 / F8 / F10 still work).

## Automatic updates (game-style: only changed files are downloaded)
The app updates itself from an https folder that you control.
1. After changing the code, run `python tools/make_release.py 1.1.1 "what changed"`. It writes `dist/`:
   `version.json` (a list of every file with its SHA-256), a `files/` copy of the program and a full zip.
2. Upload the **whole `dist/` folder** to one https address, e.g. GitHub Pages
   (`https://<you>.github.io/<repo>/version.json`) or any static host.
3. In the app open **Updates**, paste the address of `version.json`, keep "Check and install on start" on.
Each start the app compares the list with the files on disk, downloads **only the files that differ**
(a code tweak is a few KB), verifies every checksum, then swaps them in, deletes files that were removed
and restarts. Nothing is replaced unless every download verified. `config.json` and `templates/` are never
touched; replaced files are copied to `_backup/<version>/`. Python packages (OpenCV etc.) are not part of
updates - `run.bat` only installs them again if `requirements.txt` changes.
An update runs new code on your PC, so only use an address you control or fully trust.

## First-time setup (about 2 minutes)
Button images are not bundled: they depend on your resolution, UI scale and game language.
1. Run Fortnite in **windowed fullscreen** (exclusive fullscreen cannot be screen-captured).
2. Open **Templates**, choose a role, type a name, press **Capture**, switch to the game and drag a
   box around the button.
   - `start`  - the button that begins the next match (counts a game)
   - `result` - every button on the result / reward screens (Continue, Claim all, Back to lobby...)
3. Capture one template per button, per game language (`templates/ru/`, `templates/en/`).
4. **Test now** prints the current match score of every template. Raise the threshold on false clicks,
   lower it on misses (default 0.80). Then press **Start** or **F7**.

Games = start-button clicks. Cycles = games that reached a result screen.

## Files
- `run.bat` launcher · `app.py` GUI + CLI · `core.py` matching/engine · `winio.py` Windows capture, input, hotkeys
- `updater.py` self-update · `tools/make_release.py` builds update packages
- `i18n.py` all translations · `assets/` original logo (`tools/make_logo.py` regenerates it)
- `tests/` engine, updater and GUI-smoke tests

## Important
- Automating gameplay is against Epic Games' terms; accounts using it can be suspended. The anti-AFK
  input is the part most likely to be noticed. Use at your own risk.
- No license-key / online check is included.
- Not affiliated with Epic Games. The logo is original artwork.
