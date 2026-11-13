// service-worker.js — keeps a copy of the app's files on the phone, so the app still opens with no internet.
// It always tries the internet first (so you get the newest version), and uses the saved copy only when offline.
// API calls (/api/...) are never saved here: money data always comes fresh from the server.
// Other websites (e.g. the Chart.js CDN) are not cached either: offline, the Loans graphs are simply hidden.

const CACHE_NAME = "my-money-v15"; // change the number when you want every phone to start fresh
const APP_FILES = [
  "index.html",
  "login.html",
  "style.css",
  "i18n.js",
  "lang/en.json", // languages: cached so they work offline
  "lang/fr.json",
  "lang/mfe.json",
  "api.js",
  "app.js",
  "budget-calc.js",
  "money-tab.js",
  "targets-tab.js",
  "loan-calc.js",
  "loans-tab.js",
  "game-calc.js",
  "arcade-tab.js",
  "login.js",
  "manifest.json",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/apple-touch-icon.png",
];

// First install: save all the app files
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_FILES)));
  self.skipWaiting();
});

// New version: delete old saved copies
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)))
    )
  );
  self.clients.claim();
});

// Every request: try the internet, keep a fresh copy, fall back to the saved copy when offline
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isOurFile = url.origin === self.location.origin && !url.pathname.startsWith("/api/");
  if (event.request.method !== "GET" || !isOurFile) {
    return; // let the browser handle it normally
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request, { ignoreSearch: true }))
  );
});
