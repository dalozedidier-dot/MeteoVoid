const CACHE_NAME = "meteovoid-stormscope-static-v5";
const STATIC_ASSETS = [
  "./",
  "./index.html",
  "./europe.html",
  "./methodology.html",
  "./assets/app.css",
  "./assets/app.js",
  "./assets/regions.js",
  "./assets/site-api-adapter.js",
  "./assets/alert-watch-panels.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => undefined)
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
      )
      .catch(() => undefined)
  );
  self.clients.claim();
});

function networkFirst(request) {
  return fetch(request)
    .then((response) => {
      const clone = response.clone();
      caches
        .open(CACHE_NAME)
        .then((cache) => cache.put(request, clone))
        .catch(() => undefined);
      return response;
    })
    .catch(() => caches.match(request));
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;

  if (
    url.pathname.includes("/api/") ||
    url.pathname.includes("/assets/") ||
    url.pathname.endsWith(".html") ||
    url.pathname.endsWith("/")
  ) {
    event.respondWith(networkFirst(event.request));
    return;
  }

  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
});
