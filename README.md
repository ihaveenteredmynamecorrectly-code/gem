# Gemini Free-Tier Chat

A small, self-contained web chat app that talks to Google Gemini on the **free tier**
using an always-free model (`gemini-flash-lite-latest`, with fallbacks
`gemini-3.5-flash-lite` / `gemini-3.1-flash-lite`). Because the free tier is
rate-limited, the app handles 429s automatically with exponential backoff and
gracefully falls back across model aliases if the API deprecates one.

## Install as an app (Android APK / PWA)

This app ships as both an **installable PWA** and a **signed Android APK**
(Trusted Web Activity). The APK wraps the live HTTPS site, so the Gemini API
key stays server-side — it is **not** embedded in the APK.

### Pre-built APK
A signed APK is at `gemini-chat.apk` (package `dev.allhands.gemini_chat`,
version 1.0.0, ~1.1 MB). Install it on an Android device:

```bash
adb install gemini-chat.apk
```

Or copy it to your phone and tap the file (enable "Install unknown apps" for
your file manager first). The app opens full-screen with no browser bar **when
the server is running** and `/.well-known/assetlinks.json` matches the APK
signing key.

> **Requirement**: the backend server must be reachable over HTTPS at the host
> baked into the APK (`work-1-rrqnqpufphzbbshp.prod-runtime.all-hands.dev`).
> Start it with `python -m app.run --port 12000` before launching the app.

### "Install app" button (PWA, no APK needed)
The web page shows a `⬇ Install app` button when the browser fires the install
prompt. Tap it (or use Chrome's menu → Add to Home screen) for a quick
install without side-loading.

### Rebuild the APK from scratch
Requires JDK 17+ and the Android SDK (build-tools 36.1.0). The build is driven
by `android/twa/build_apk.exp` (an `expect` script that answers Bubblewrap's
interactive prompts):

```bash
# prerequisites: JDK (apt install openjdk-21-jdk-headless),
#                Android cmdline-tools + build-tools;36.1.0 + platforms;android-35
#                expect (apt install expect)
export ANDROID_HOME=/opt/android-sdk
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
cd android/twa
./build_apk.exp
# → produces app-release-signed.apk + app-release-bundle.aab
```

The signing keystore lives at `android/gemini-chat.keystore` (password
`android`, gitignored). To regenerate it:

```bash
keytool -genkeypair -keystore android/gemini-chat.keystore -alias gemini-chat \
  -keyalg RSA -keysize 2048 -validity 10000 -storepass android -keypass android \
  -dname "CN=Gemini Chat, OU=Dev, O=AllHands, L=SF, ST=CA, C=US"
```

Then update `ASSETLINKS_FINGERPRINTS` in `.env` with the new SHA-256 fingerprint
(`keytool -list -v -keystore android/gemini-chat.keystore -storepass android`).

### Regenerate PWA icons
```bash
python -m app.gen_icons
```
Icons are committed to `app/static/` so you only need Pillow if you change the
logo design.

## Run it

```bash
cp .env.example .env       # then edit .env and set GEMINI_API_KEY=...
pip install -r requirements.txt
python -m app.run          # serves on http://localhost:12000
```

Or with uvicorn directly:

```bash
GEMINI_API_KEY=... uvicorn app.main:app --host 0.0.0.0 --port 12000
```

## Configuration (env)

| Var                     | Default                   | Description                                      |
|-------------------------|---------------------------|--------------------------------------------------|
| `GEMINI_API_KEY`        | _(required)_              | Your Gemini API key                              |
| `GEMINI_MODEL`          | `gemini-flash-lite-latest`| Primary always-free model                        |
| `GEMINI_FALLBACK_MODELS`| `gemini-3.5-flash-lite,gemini-3.1-flash-lite` | Models tried in order if the primary is unavailable |

## How it handles rate limits

- Free tier returns `x-gemini-service-tier: standard` and enforces per-minute limits.
- On HTTP `429` the client backs off (exponential + jitter, capped at 60s),
  respecting any `Retry-After` header, then retries the same model up to
  `max_retries` times.
- If a model returns `404`/`503` (deprecation/unavailable), that model is
  circuit-opened for 5 minutes and the next fallback model is used.
- The UI surfaces rate-limit state (status dot + inline error) and tells the
  user to wait ~60s.

## Tests

Tests hit the **real** Gemini API (no mocks) when `GEMINI_API_KEY` is set and
are skipped otherwise.

```bash
pip install -r requirements.txt
pytest -q
```

## Layout

```
app/
  main.py            FastAPI app + endpoints
  gemini_client.py   Gemini REST client w/ rate-limit + fallback logic
  run.py             CLI runner
  static/index.html  Single-page chat UI
tests/test_app.py    Real-API integration tests
```
