const CACHE_NAME = "novoprint-cache-v1";
const urlsToCache = [
  "/", 
  "/static/css/style.css",
  "/static/icons/novoprint_icon_192.png",
  "/static/icons/novoprint_icon_512.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(urlsToCache);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", event => {
  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});
