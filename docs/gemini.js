// Gemini free-tier client — browser-side, with rate-limit handling.
// Mirrors app/gemini_client.py: 429 exponential backoff (jittered, respects
// Retry-After), and automatic fallback through a model alias list.
//
// NOTE (option 1 tradeoff): the API key is embedded here. There is no backend,
// so the key is visible to anyone who opens the page source. This is acceptable
// for a free-tier personal key; see the README for the server-side alternative.
const GEMINI_API_KEY = "AQ.Ab8RN6K9WX5bmydCBFWdTyCrd9g0HkkbT4HopcGi6KCi8OJCfQ";
const API_BASE = "https://generativelanguage.googleapis.com/v1beta/models";

const MODELS = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"];
const MAX_RETRIES = 5;
const BASE_BACKOFF = 1.5;
const MAX_BACKOFF = 60;

let deadUntil = {}; // model -> epoch ms when cooldown ends
let activeModel = null;

function availableModels() {
  const now = Date.now();
  return MODELS.filter((m) => (deadUntil[m] || 0) <= now);
}

function backoff(attempt) {
  const raw = Math.min(MAX_BACKOFF, BASE_BACKOFF * Math.pow(2, attempt - 1));
  return Math.random() * raw; // full jitter
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function parseRetryAfter(resp) {
  const ra = resp.headers.get("retry-after") || resp.headers.get("Retry-After");
  if (!ra) return null;
  const n = parseFloat(ra);
  return isNaN(n) ? null : n;
}

function errMessage(resp) {
  try { return resp.json ? "" : ""; } catch { return ""; }
}

async function generateWithModel(model, body) {
  const url = `${API_BASE}/${model}:generateContent?key=${encodeURIComponent(GEMINI_API_KEY)}`;
  let attempt = 0;
  while (true) {
    attempt++;
    let resp;
    try {
      resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (e) {
      if (attempt > MAX_RETRIES) throw new Error(`transport error: ${e}`);
      await sleep(backoff(attempt) * 1000);
      continue;
    }

    if (resp.status === 200) {
      activeModel = model;
      const data = await resp.json();
      const parts = data?.candidates?.[0]?.content?.parts || [];
      const text = parts.filter((p) => p.text).map((p) => p.text).join("").trim();
      const tokens = data?.usageMetadata?.totalTokenCount ?? null;
      return { text, model, tokens };
    }

    const retryAfter = parseRetryAfter(resp);

    if (resp.status === 429) {
      const wait = retryAfter || backoff(attempt);
      deadUntil[model] = Date.now() + wait * 1000;
      if (attempt > MAX_RETRIES) throw { rateLimited: true, wait };
      await sleep(wait * 1000);
      continue;
    }

    if (resp.status === 404 || resp.status === 503) {
      deadUntil[model] = Date.now() + 300 * 1000;
      let msg = `model ${model} unavailable (HTTP ${resp.status})`;
      try { const j = await resp.json(); msg = j?.error?.message || msg; } catch {}
      throw { modelUnavailable: true, message: msg };
    }

    let msg = `HTTP ${resp.status}`;
    try { const j = await resp.json(); msg = j?.error?.message || msg; } catch {}

    // Auth errors are NOT transient — never retry, fail fast with a clear note.
    if (resp.status === 401 || resp.status === 403) {
      throw { authError: true, status: resp.status, message: msg };
    }

    if (attempt > MAX_RETRIES) throw new Error(`model ${model}: ${msg}`);
    await sleep(backoff(attempt) * 1000);
  }
}

async function generate(prompt, { system, temperature = 0.7, max_tokens = 1024 } = {}) {
  const body = {
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    generationConfig: { temperature, maxOutputTokens: max_tokens },
  };
  if (system) body.systemInstruction = { parts: [{ text: system }] };

  const models = availableModels();
  if (models.length === 0) {
    throw { rateLimited: true, wait: 0, allDead: true };
  }

  let lastErr = null;
  for (const model of models) {
    try {
      return await generateWithModel(model, body);
    } catch (e) {
      lastErr = e;
      // Auth errors affect all models (same key) — don't bother trying the rest.
      if (e?.authError) break;
      if (e?.rateLimited) continue;
      if (e?.modelUnavailable) continue;
      continue;
    }
  }
  throw lastErr || { allDead: true };
}

export { generate, MODELS, activeModel };
