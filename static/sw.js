// Service worker mínimo: existe solo para que el navegador ofrezca "Instalar app".
// No cachea nada a propósito — toda request pasa directo a la red, para no servir datos
// desactualizados en una app que cambia constantemente (proyectos, observaciones, etc.).
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
