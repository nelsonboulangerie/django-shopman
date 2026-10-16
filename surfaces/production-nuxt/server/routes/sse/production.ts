// Rota SSE same-origin da Produção: /sse/production → streaming do eventstream do
// Django (canal /events/production/ → backstage-production-main), que avisa a cada
// lote planejado, aberto, ajustado ou fechado. Transporte na layer operator-kit
// (server/utils/eventStream.ts, auto-importado).
export default defineEventHandler((event) => proxyEventStream(event, "/events/production/"));
