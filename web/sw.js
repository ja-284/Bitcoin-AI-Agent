// Offline shell for the installable app. Network first for everything, so a new version and fresh numbers always win
// when there is a connection; the cache only answers when the network does not, so the app still opens offline.
const CACHE = "bitcoin-agent-shell-v2";
const SHELL = ["./", "index.html", "css/tokens.css", "css/app.css", "js/app.js", "js/ui.js", "js/data.js", "js/chart.js",
  "js/pages.js", "assets/icon.svg", "manifest.webmanifest"];

self.addEventListener("install", (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL))); self.skipWaiting(); });
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
        return res;
      })
      .catch(() => caches.match(e.request)),
  );
});
