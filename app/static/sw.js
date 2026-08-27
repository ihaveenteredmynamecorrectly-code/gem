// Minimal service worker for the Gemini Free-Tier Chat PWA.
// Strategy: app shell (HTML/CSS/JS/icons) is cache-first; API calls always
// go to the network (never cache live model responses).
const CACHE = "gemini-chat-v1";
const SHELL = [
  "./",
  "./static/manifest.webmanifest",
  "./static/icon-192.png",
  "./static/icon-512.png",
  "./static/icon-maskable-192.png",
  "./static/icon-maskable-512.png",
  "./static/apple-touch-icon.png",
  "./static/favicon.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Never cache API responses — they must always hit the live model.
  if (url.pathname.startsWith("/api/")) {
    return;
  }
  // App shell: cache-first, then network (and cache the response).
  e.respondWith(
    caches.match(e.request).then((cached) => {
      if (cached) return cached;
      return fetch(e.request).then((resp) => {
        if (resp && resp.status === 200 && resp.type === "basic") {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return resp;
      }).catch(() => cached);
    })
  );
});
