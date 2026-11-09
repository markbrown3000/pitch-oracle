// Pitch Oracle offline cache. Pages and data always try the network first (so you get the latest),
// and fall back to the last copy when you're offline or the network is very slow.
const CACHE = "pitch-oracle-v1";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())) });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())) });
const strip = req => { const u = new URL(req.url); u.search = ""; return u.toString() };
self.addEventListener("fetch", e => {
  const req = e.request; const u = new URL(req.url);
  if (req.method !== "GET" || u.origin !== location.origin) return;            // other sites (ESPN, Kalshi…) go straight to the network
  const isStatic = /\.(png|webmanifest)$/.test(u.pathname);
  if (isStatic) { e.respondWith(caches.match(req, { ignoreSearch: true }).then(r => r || fetch(req))); return }
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const net = await Promise.race([fetch(req), new Promise((_, rej) => setTimeout(() => rej(new Error("slow")), req.mode === "navigate" ? 6000 : 15000))]);
      if (net && net.ok) cache.put(strip(req), net.clone());
      return net;
    } catch (err) {
      const hit = await cache.match(strip(req)) || (req.mode === "navigate" ? await cache.match("./index.html") : null);
      if (hit) return hit;
      throw err;
    }
  })());
});
