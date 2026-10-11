// Platoon 5 Digital Album -- Service Worker
//
// This is a server-rendered Flask app, not a single-page app, so the
// service worker's job is deliberately modest: make the app installable,
// cache the static "app shell" (CSS/JS/icons) for fast repeat loads, and
// show a friendly offline page instead of the browser's default error
// when there's no network for a page navigation. It does NOT try to cache
// or serve dynamic/authenticated pages offline -- profile data, the
// directory, admin actions, etc. always need a live connection, and
// pretending otherwise would risk showing stale or private data.

const CACHE_NAME = "platoon5-shell-v1";
const APP_SHELL = [
  "/static/css/style.css",
  "/static/js/app.js",
  "/static/img/icon-192.png",
  "/static/img/icon-512.png",
  "/static/img/placeholder-avatar.png",
  "/static/img/placeholder-logo.png",
  "/offline",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only ever handle simple GET requests -- never intercept POSTs (form
  // submissions, CSRF-protected actions) or cross-origin requests.
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) {
    return;
  }

  // Page navigations: try the network first (this app is dynamic and
  // privacy-sensitive -- always prefer fresh, authenticated content), and
  // only fall back to the offline page if there's truly no connection.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/offline"))
    );
    return;
  }

  // Static assets (CSS/JS/images): cache-first for speed, populating the
  // cache on first fetch for anything not already pre-cached.
  if (request.url.includes("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        });
      })
    );
  }
});
