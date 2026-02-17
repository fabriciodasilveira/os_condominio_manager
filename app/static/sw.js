const CACHE_NAME = "condominio-os-v17";
const ASSETS = [
  "/",
  "/manifest.json",
  "/static/styles.css",
  "/static/app.js",
  "/static/logo.png",
  "/static/icon-192.png",
  "/static/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});

self.addEventListener("push", (event) => {
  const data = event.data ? event.data.json() : { title: "Atualização", body: "Nova notificação" };
  event.waitUntil(
    self.registration.showNotification(data.title || "Condomínio OS", {
      body: data.body || "Status atualizado",
      icon: "/static/icon-192.png",
      badge: "/static/icon-192.png",
      data,
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow("/"));
});
