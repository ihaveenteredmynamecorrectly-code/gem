"""FastAPI app: a single-page Gemini chat with free-tier rate-limit UX."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .gemini_client import AllModelsUnavailableError, GeminiClient, RateLimitError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.client = GeminiClient.from_env()
        logger.info("Gemini client ready; models=%s", app.state.client.models)
    except Exception as e:
        logger.error("Failed to init Gemini client: %s", e)
        app.state.client = None
    yield
    if getattr(app.state, "client", None):
        await app.state.client.aclose()


app = FastAPI(title="Gemini Free-Tier Chat", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    client: GeminiClient | None = request.app.state.client
    models = client.models if client else []
    return templates.TemplateResponse(
        request,
        "index.html",
        {"models": models, "configured": client is not None},
    )


@app.get("/api/health")
async def health(request: Request):
    client: GeminiClient | None = request.app.state.client
    return {
        "ok": client is not None,
        "models": client.models if client else [],
        "active_model": client.active_model if client else None,
    }


# Digital Asset Links for the Android TWA (Trusted Web Activity) so the app
# opens full-screen without a browser bar. The fingerprint(s) of the APK signing
# key are injected via the ASSETLINKS_FINGERPRINTS env var (comma-separated).
@app.get("/.well-known/assetlinks.json", include_in_schema=False)
async def assetlinks(request: Request):
    fps = [f.strip() for f in os.environ.get("ASSETLINKS_FINGERPRINTS", "").split(",") if f.strip()]
    statements = []
    for fp in fps:
        statements.append({
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": "dev.allhands.gemini_chat",
                "sha256_cert_fingerprints": [fp],
            },
        })
    body = json.dumps(statements)
    return Response(content=body, media_type="application/json")


@app.post("/api/chat")
async def chat(request: Request):
    client: GeminiClient | None = request.app.state.client
    if client is None:
        return JSONResponse({"error": "Gemini API key is not configured on the server."}, status_code=503)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body."}, status_code=400)

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"error": "prompt is required."}, status_code=400)
    if len(prompt) > 8000:
        return JSONResponse({"error": "prompt too long (max 8000 chars)."}, status_code=400)

    system = (payload.get("system") or "").strip() or None
    temperature = _clamp(payload.get("temperature", 0.7), 0.0, 2.0)
    max_tokens = int(_clamp(payload.get("max_tokens", 1024), 16, 8192))

    try:
        resp = await asyncio.wait_for(
            client.generate(
                prompt,
                system=system,
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
            timeout=90,
        )
    except asyncio.TimeoutError:
        return JSONResponse({"error": "Request timed out. The free tier may be busy — try again."}, status_code=504)
    except RateLimitError:
        return JSONResponse(
            {"error": "Free-tier rate limit reached. Please wait a minute and try again.", "rate_limited": True},
            status_code=429,
        )
    except AllModelsUnavailableError as e:
        return JSONResponse(
            {"error": str(e), "rate_limited": "rate" in str(e).lower() or "429" in str(e)},
            status_code=503,
        )
    except Exception as e:
        logger.exception("unexpected chat error")
        return JSONResponse({"error": f"Unexpected error: {e}"}, status_code=500)

    return {
        "text": resp.text,
        "model": resp.model,
        "tokens": resp.tokens,
    }


def _clamp(v, lo, hi):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, f))
