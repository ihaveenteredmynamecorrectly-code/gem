"""Gemini REST client with free-tier rate-limit handling.

The free tier (`x-gemini-service-tier: standard`) enforces per-minute request
limits. When the API returns 429 (or a transport error) we retry with
exponential backoff, respecting any Retry-After header, and automatically fall
back through a configured list of model aliases if the primary model is no
longer available (the API periodically deprecates model versions for free
users).
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class RateLimitError(Exception):
    """Raised when the rate limit is exhausted after all retries."""


class AllModelsUnavailableError(Exception):
    """Raised when every configured model returns a hard error."""


@dataclass
class GeminiResponse:
    text: str
    model: str
    tokens: int | None


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        primary_model: str = "gemini-flash-lite-latest",
        fallback_models: list[str] | None = None,
        max_retries: int = 5,
        base_backoff: float = 1.5,
        max_backoff: float = 60.0,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.models = [primary_model, *(fallback_models or [])]
        # Track which models are temporarily (rate-limited) or long-term (404) down.
        self._dead_until: dict[str, float] = {}
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
        self._active_model: str | None = None

    @classmethod
    def from_env(cls) -> "GeminiClient":
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Put it in .env or export it."
            )
        primary = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest").strip() or "gemini-flash-lite-latest"
        fallback = [m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODES", os.environ.get("GEMINI_FALLBACK_MODELS", "")).split(",") if m.strip()]
        return cls(key, primary, fallback)

    @property
    def active_model(self) -> str | None:
        return self._active_model

    def _available_models(self) -> list[str]:
        now = time.monotonic()
        return [m for m in self.models if self._dead_until.get(m, 0) <= now]

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_output_tokens: int = 1024,
    ) -> GeminiResponse:
        contents: list[dict] = [{"role": "user", "parts": [{"text": prompt}]}]
        body: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        last_err: Exception | None = None
        for model in self._available_models():
            try:
                return await self._generate_with_model(model, body)
            except RateLimitError as e:
                last_err = e
                continue
            except AllModelsUnavailableError as e:
                last_err = e
                continue
            except httpx.HTTPError as e:
                last_err = e
                logger.warning("transport error for %s: %s", model, e)
                continue
        if last_err is None:
            raise AllModelsUnavailableError("No Gemini models are currently available (all rate-limited or down).")
        if isinstance(last_err, RateLimitError):
            raise last_err
        raise AllModelsUnavailableError(str(last_err)) from last_err

    async def _generate_with_model(self, model: str, body: dict) -> GeminiResponse:
        url = f"{API_BASE}/{model}:generateContent"
        params = {"key": self.api_key}
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self._client.post(url, params=params, json=body)
            except httpx.HTTPError:
                if attempt > self.max_retries:
                    raise
                await asyncio.sleep(self._backoff(attempt))
                continue

            if resp.status_code == 200:
                self._active_model = model
                return self._parse(resp, model)

            retry_after = self._parse_retry_after(resp)

            if resp.status_code == 429:
                wait = retry_after or self._backoff(attempt)
                self._dead_until[model] = time.monotonic() + wait
                logger.info("model %s rate limited (429); cooling down %.1fs", model, wait)
                if attempt > self.max_retries:
                    raise RateLimitError(f"model {model} exhausted retries after 429")
                await asyncio.sleep(wait)
                continue

            if resp.status_code in (404, 503):
                self._dead_until[model] = time.monotonic() + 300
                raise AllModelsUnavailableError(
                    f"model {model} unavailable (HTTP {resp.status_code}): {self._err_message(resp)}"
                )

            if attempt > self.max_retries:
                raise httpx.HTTPStatusError(
                    f"model {model} HTTP {resp.status_code}: {self._err_message(resp)}",
                    request=resp.request, response=resp,
                )
            await asyncio.sleep(self._backoff(attempt))

    def _parse(self, resp: httpx.Response, model: str) -> GeminiResponse:
        data = resp.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
        usage = data.get("usageMetadata", {})
        tokens = usage.get("totalTokenCount")
        return GeminiResponse(text=text, model=model, tokens=tokens)

    @staticmethod
    def _err_message(resp: httpx.Response) -> str:
        try:
            return resp.json().get("error", {}).get("message", resp.text[:200])
        except Exception:
            return resp.text[:200]

    @staticmethod
    def _parse_retry_after(resp: httpx.Response) -> float | None:
        ra = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
        if not ra:
            return None
        try:
            return float(ra)
        except ValueError:
            return None

    def _backoff(self, attempt: int) -> float:
        raw = min(self.max_backoff, self.base_backoff * (2 ** (attempt - 1)))
        # Full jitter to avoid thundering herd on shared rate limits.
        return random.uniform(0, raw)
