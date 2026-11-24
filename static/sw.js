// Service worker de Revisor CNR.
// - No cachea nada a propósito: toda request pasa directo a la red, para no servir datos
//   desactualizados en una app que cambia constantemente (proyectos, observaciones, etc.).
// - Único añadido (nov-2026): si una CARGA DE PÁGINA (navegación GET) falla por red/DNS
//   (ej. DNS_PROBE_FINISHED_NXDOMAIN en la red de la oficina), muestra un aviso propio que reintenta
//   solo y vuelve a la página en cuanto la red responde, en vez de dejar la pantalla de error de
//   Chrome hasta que el usuario recargue. NO toca envíos de formularios (POST) ni otras requests,
//   para no reenviar ni duplicar nada.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

const AVISO_SIN_CONEXION = `<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sin conexión — Revisor CNR</title>
<style>
 :root{color-scheme:light dark}
 body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f5f5f7;color:#1d1d1f}
 @media (prefers-color-scheme:dark){body{background:#1c1c1e;color:#f5f5f7}}
 .caja{text-align:center;padding:2rem;max-width:26rem}
 h1{font-size:1.15rem;margin:0 0 .5rem}
 p{margin:.3rem 0;font-size:.92rem;opacity:.75}
 .punto{display:inline-block;width:.6rem;height:.6rem;border-radius:50%;background:#d69e2e;margin-right:.45rem;
        animation:p 1.2s ease-in-out infinite}
 @keyframes p{50%{opacity:.25}}
 button{margin-top:1rem;padding:.45rem 1rem;border-radius:8px;border:1px solid rgba(128,128,128,.5);
        background:transparent;color:inherit;font:inherit;cursor:pointer}
</style></head><body><div class="caja">
<h1><span class="punto"></span>Sin conexión con el servidor</h1>
<p>Reintentando automáticamente. La página volverá sola cuando la red responda.</p>
<button type="button" onclick="reintentar()">Reintentar ahora</button></div>
<script>
 var ocupado = false;
 function reintentar() {
   if (ocupado) return; ocupado = true;
   fetch(location.href, {cache: "no-store", redirect: "manual"})
     .then(function () { location.reload(); })
     .catch(function () { ocupado = false; });
 }
 setInterval(reintentar, 4000);
</script></body></html>`;

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.mode !== "navigate" || req.method !== "GET") return;   // solo cargas de página
  event.respondWith(
    fetch(req).catch(() => new Response(AVISO_SIN_CONEXION, {
      status: 503, headers: {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"},
    }))
  );
});
