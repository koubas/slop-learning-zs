// Service worker, který k odpovědím ze stejného originu přidá hlavičky
// COOP/COEP. Díky tomu je stránka cross-origin izolovaná (a má přístup
// k SharedArrayBuffer) i na obyčejném `python3 -m http.server` nebo GitHub Pages.
// Cizí originy (jsdelivr) se neproxují, ty posílají CORP/CORS samy.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (new URL(req.url).origin !== self.location.origin) return;
  if (req.cache === "only-if-cached" && req.mode !== "same-origin") return;
  e.respondWith(
    fetch(req).then((res) => {
      if (res.status === 0) return res;
      const headers = new Headers(res.headers);
      headers.set("Cross-Origin-Embedder-Policy", "require-corp");
      headers.set("Cross-Origin-Opener-Policy", "same-origin");
      return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
    })
  );
});
