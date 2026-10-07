// Service worker do Painel de Agentes (TekLabs Digital).
// Guarda só a "casca" do app para ele abrir mesmo com o servidor desligado.
// Os dados (/api/...) nunca vêm do cache: são sempre lidos ao vivo.
const VERSAO = "painel-v2";
const CASCA = ["/", "/manifest.webmanifest", "/icons/icone.svg", "/icons/logo-teklabs.svg",
               "/icons/icone-192.png", "/icons/icone-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSAO).then((c) => c.addAll(CASCA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((nomes) => Promise.all(nomes.filter((n) => n !== VERSAO).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  // Rede primeiro (pega a versão nova da página); cache só se o servidor estiver fora.
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        if (r.ok) {  // erro (404, 500) nunca substitui a cópia boa guardada para o modo offline
          const copia = r.clone();
          caches.open(VERSAO).then((c) => c.put(e.request, copia));
        }
        return r;
      })
      .catch(() => caches.match(e.request))
  );
});
