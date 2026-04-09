# Distribution Notes

**Internal — not user-facing.** Last updated: April 2026. Applies to Waveform v2 (CustomTkinter build).

---

## Environment variables

Waveform reads credentials from a `.env` file at the project root via `python-dotenv`. The full set of recognized variables is in `.env.example`. Required variables:

```
SPOTIFY_CLIENT_ID
SPOTIFY_CLIENT_SECRET
SPOTIFY_REDIRECT_URI
GOOGLE_GENERATIVE_AI_API_KEY
```

On a developer machine, copy `.env.example` to `.env` and fill it in. `python-dotenv` loads it automatically when `waveform.app.main` starts.

For packaged distributions (see below), the `.env` file is not bundled. Users must set these variables via one of:

1. A `.env` file they place next to the app bundle or executable (supported — `python-dotenv` searches the working directory at launch).
2. System environment variables set before launching the app (macOS: `launchctl setenv` or shell profile; Windows: System Properties > Environment Variables).

The Settings screen in the app provides a credential entry UI that writes to `~/.waveform/settings.json` as an alternative to the `.env` file. Both sources are read; `.env` takes precedence if both are present.

---

## macOS — PyInstaller .app bundle

### Prerequisites

```bash
pip install pyinstaller
```

PyInstaller must be run from the activated virtualenv that has all dependencies installed.

### Basic build

From the project root:

```bash
pyinstaller \
  --name "Waveform" \
  --windowed \
  --icon assets/icons/waveform.icns \
  --add-data "waveform/assets:waveform/assets" \
  --add-data "waveform/prompts:waveform/prompts" \
  waveform/__main__.py
```

`--windowed` suppresses the terminal window on launch. Output lands in `dist/Waveform.app`.

Key flags to add as the build matures:

- `--onefile` — single-file executable instead of a folder bundle (slower cold start, easier distribution)
- `--hidden-import customtkinter` — CustomTkinter's dynamic imports are not always auto-detected
- `--collect-data customtkinter` — ensures CustomTkinter's theme JSON files are bundled
- `--collect-data pygame` — ensures pygame's SDL dylibs are included

If the app fails to find assets at runtime, add explicit `--add-data` entries for any directory PyInstaller misses. Use `sys._MEIPASS` as the base path in code when resolving bundled asset paths:

```python
import sys, os
base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
asset_path = os.path.join(base, "waveform", "assets", "fonts", "Inter.ttf")
```

### macOS notarization — deferred to Phase 2 beta

Notarization is required for distribution to users outside your own machine on macOS 10.15+. Without it, Gatekeeper blocks the app on first open. The steps are documented here for Phase 2 but are not done for the internal alpha.

**What you need:**
- Apple Developer Program membership ($99/year)
- Xcode command-line tools (`xcode-select --install`)
- An "Application" certificate from the Apple Developer portal, installed in your keychain

**Step 1 — Code sign the bundle:**

```bash
codesign \
  --deep \
  --force \
  --verify \
  --verbose \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  --options runtime \
  dist/Waveform.app
```

`--options runtime` enables the hardened runtime, which is required for notarization.

**Step 2 — Create a zip for submission:**

```bash
ditto -c -k --keepParent dist/Waveform.app dist/Waveform.zip
```

**Step 3 — Submit for notarization:**

```bash
xcrun notarytool submit dist/Waveform.zip \
  --apple-id "your@apple.id" \
  --team-id "TEAMID" \
  --password "app-specific-password" \
  --wait
```

Use an app-specific password from [appleid.apple.com](https://appleid.apple.com), not your main Apple ID password.

**Step 4 — Staple the notarization ticket:**

```bash
xcrun stapler staple dist/Waveform.app
```

**Step 5 — Package as .dmg for distribution:**

```bash
hdiutil create \
  -volname "Waveform" \
  -srcfolder dist/Waveform.app \
  -ov -format UDZO \
  dist/Waveform.dmg
```

The .dmg itself does not need to be re-signed after stapling the .app.

---

## Windows — deferred to Phase 2

Windows packaging is Phase 2 work. The approach will be PyInstaller producing a `.exe` (likely `--onefile` for simplicity). Known issues to address at that time:

- pygame SDL DLLs must be explicitly collected
- CustomTkinter theme data must be bundled
- Windows code signing requires an EV code signing certificate (typically $300-500/year from DigiCert, Sectigo, etc.) to avoid SmartScreen warnings
- The `.env` file workflow is less familiar to Windows users; the Settings screen credential UI should be the primary path on Windows

Track this work in the Phase 2 planning epic.
