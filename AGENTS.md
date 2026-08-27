# Project Notes — Gemini Free-Tier Chat

## What this is
A FastAPI single-page chat app that talks to Google Gemini on the **free tier**
using an always-free model. Built to be robust against free-tier rate limits.

## Key facts (learned while building)
- The `/v1beta/models` list is **stale** — it lists models that return 404 with
  "no longer available to new users". The error message tells you the
  replacement model to use.
- Free tier is identified by the response header `x-gemini-service-tier: standard`.
- Working always-free models (as of build): `gemini-flash-lite-latest` (stable
  alias), `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`.
  `gemini-2.5-flash` and `gemini-2.5-flash-lite` are **deprecated** for new users.
- 429s are the primary rate-limit signal; respect `Retry-After` when present.

## Run
```bash
cp .env.example .env  # set GEMINI_API_KEY
pip install -r requirements.txt
python -m app.run --port 12000
```

## Test
```bash
GEMINI_API_KEY=... pytest -q   # hits the real API; skipped without a key
```

## Architecture
- `app/gemini_client.py` — async Gemini REST client. Handles 429 backoff
  (exp + jitter, cap 60s, honors Retry-After), per-model circuit opening on
  404/503 (5-min cooldown), and automatic fallback across model aliases.
- `app/main.py` — FastAPI endpoints: `/`, `/api/health`, `/api/chat`.
- `app/static/index.html` — single-page chat UI (status dot, temp/max-tokens,
  optional system instruction, example chips).

## Conventions
- Tests exercise **real** API paths (no mocks); skipped when no API key.
- Run a coroutine and its httpx `aclose()` in the **same** event loop (calling
  `aclose()` in a different loop raises `RuntimeError: Event loop is closed`).
  The tests use a fresh `asyncio.new_event_loop()` per case to avoid this.
- Secrets live only in `.env` (gitignored) or env vars — never committed.

## APK / installable app
The app ships as a **PWA** (manifest + service worker + icons in `app/static/`)
**and** a signed **Android APK** built via Bubblewrap (Trusted Web Activity).

**Key design decision**: the APK is a TWA that wraps the live HTTPS site. The
Gemini API key stays server-side (in `.env`) — it is **never** embedded in the
APK. The APK only works when the backend is reachable at the host baked into
`twa-manifest.json`.

Build artifacts (all gitignored):
- `gemini-chat.apk` — signed APK at project root (package `dev.allhands.gemini_chat`)
- `android/twa/` — Bubblewrap TWA project (`twa-manifest.json`, Gradle project)
- `android/twa/build_apk.exp` — `expect` script that drives Bubblewrap's
  interactive prompts non-interactively (committed; the only tracked file in `android/`)
- `android/gemini-chat.keystore` — signing key (password `android`, gitignored)
- `android/twa/app-release-signed.apk`, `app-release-bundle.aab` — build outputs

Toolchain installed in this sandbox:
- JDK 21 (`/usr/lib/jvm/java-21-openjdk-amd64`)
- Android SDK (`/opt/android-sdk`): cmdline-tools, build-tools 35.0.0 + 36.1.0,
  platform-tools, platforms;android-35
- `expect` for non-interactive Bubblewrap builds
- `~/.bubblewrap/config.json` records the JDK + SDK paths so Bubblewrap skips
  its install prompts

`/.well-known/assetlinks.json` is served by the FastAPI app; its
`sha256_cert_fingerprints` come from the `ASSETLINKS_FINGERPRINTS` env var
(comma-separated). This must match the APK signing key for the TWA to open
without a URL bar.
