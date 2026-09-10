// Rota SSE same-origin do sino de alertas: /sse/alerts → streaming do
// eventstream do Django (canal /events/alerts/ → backstage-alerts-main).
// Transporte na layer operator-kit (server/utils/eventStream.ts, auto-importado).
export default defineEventHandler((event) => proxyEventStream(event, "/events/alerts/"));
