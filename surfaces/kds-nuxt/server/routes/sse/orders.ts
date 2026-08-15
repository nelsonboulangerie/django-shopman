// Rota SSE same-origin do painel de retirada do cliente: /sse/orders →
// streaming do eventstream do Django (canal /events/orders/). Transporte
// na layer operator-kit (server/utils/eventStream.ts, auto-importado).
export default defineEventHandler((event) => proxyEventStream(event, "/events/orders/"));
