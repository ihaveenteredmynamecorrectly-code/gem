"""Tests for the Gemini client against the real API and the FastAPI app.

These hit the real Gemini API when GEMINI_API_KEY is set, exercising real code
paths (no mocks). They are skipped automatically if no key is available so CI
without credentials still passes.
"""
import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from app.gemini_client import AllModelsUnavailableError, GeminiClient
from app.main import app


def _have_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


pytestmark = pytest.mark.skipif(not _have_key(), reason="GEMINI_API_KEY not set")


def _run(coro):
    """Run a coroutine to completion, closing the httpx AsyncClient in the same loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_client_initializes_from_env():
    client = GeminiClient.from_env()
    assert client.api_key
    assert client.models
    assert client.models[0]
    _run(client.aclose())


def test_real_generate_returns_text_and_model():
    client = GeminiClient.from_env()

    async def go():
        try:
            resp = await client.generate("Reply with exactly: hello world", temperature=0.0)
            assert resp.text, "expected non-empty text"
            assert resp.model in client.models
        finally:
            await client.aclose()

    _run(go())


def test_real_generate_with_system_instruction():
    client = GeminiClient.from_env()

    async def go():
        try:
            resp = await client.generate(
                "What is your name?",
                system="You are a helpful assistant named Pip. Always introduce yourself as Pip.",
                temperature=0.0,
            )
            assert resp.text
        finally:
            await client.aclose()

    _run(go())


def test_fallback_used_when_primary_unknown():
    key = os.environ["GEMINI_API_KEY"]
    client = GeminiClient(
        key,
        primary_model="this-model-does-not-exist-xyz",
        fallback_models=["gemini-flash-lite-latest", "gemini-3.5-flash-lite"],
    )

    async def go():
        try:
            resp = await client.generate("Say hi", temperature=0.0)
            assert resp.model != "this-model-does-not-exist-xyz"
            assert resp.text
        finally:
            await client.aclose()

    _run(go())


def test_all_unavailable_raises():
    key = os.environ["GEMINI_API_KEY"]
    client = GeminiClient(key, primary_model="nope-1", fallback_models=["nope-2", "nope-3"])

    async def go():
        try:
            with pytest.raises(AllModelsUnavailableError):
                await client.generate("hi")
        finally:
            await client.aclose()

    _run(go())


def test_app_health_endpoint_ok():
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        j = r.json()
        if j["ok"]:
            assert isinstance(j["models"], list) and j["models"]


def test_app_index_page_renders():
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "Gemini" in r.text


def test_app_chat_endpoint_requires_prompt():
    with TestClient(app) as c:
        r = c.post("/api/chat", json={})
        assert r.status_code == 400


def test_app_chat_endpoint_rejects_oversize():
    with TestClient(app) as c:
        r = c.post("/api/chat", json={"prompt": "x" * 8001})
        assert r.status_code == 400


def test_app_chat_endpoint_real_call():
    with TestClient(app) as c:
        r = c.post("/api/chat", json={"prompt": "Reply with exactly: pong", "temperature": 0.0})
        assert r.status_code in (200, 429, 503), r.text
        if r.status_code == 200:
            j = r.json()
            assert "text" in j
            assert "model" in j
