/* Folio service worker: offline app shell, cached fonts, and the Android share target. */
const SHELL = "folio-shell-v4";
const FONTS = "folio-fonts-v1";
const ASSETS = ["/", "/index.html", "/styles.css", "/editor.css", "/app.js", "/editor.js", "/manifest.webmanifest", "/icons/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((k) => k.startsWith("folio-shell-") && k !== SHELL).map((k) => caches.delete(k)),
  )).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  if (e.request.method === "POST" && url.pathname === "/share-target") {
    e.respondWith((async () => {
      const form = await e.request.formData();
      const cache = await caches.open("folio-shared");
      for (const k of await cache.keys()) await cache.delete(k);
      let i = 0;
      for (const f of form.getAll("files")) {
        if (!(f instanceof File)) continue;
        await cache.put(`/shared/${i++}`, new Response(f, { headers: { "Content-Type": f.type || "application/octet-stream", "X-Name": encodeURIComponent(f.name) } }));
      }
      return Response.redirect("/#/shared", 303);
    })());
    return;
  }

  if (e.request.method !== "GET") return;
  if (url.origin === location.origin && url.pathname.startsWith("/api/")) return; // never cache tool traffic

  if (url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com" || url.hostname === "cdnjs.cloudflare.com") {
    e.respondWith(caches.open(FONTS).then(async (c) => {
      const hit = await c.match(e.request);
      const net = fetch(e.request).then((r) => { if (r.ok) c.put(e.request, r.clone()); return r; }).catch(() => hit);
      return hit || net;
    }));
    return;
  }

  if (url.origin === location.origin) {
    e.respondWith(fetch(e.request).then((r) => {
      if (r.ok) { const copy = r.clone(); caches.open(SHELL).then((c) => c.put(e.request, copy)); }
      return r;
    }).catch(() => caches.match(e.request).then((m) => m || caches.match("/index.html"))));
  }
});
