// Rota SSE same-origin do PDV: /sse/cash → streaming do eventstream do Django
// (canal /events/cash/ — pedido de troco, devolução pendente, turno aberto/
// fechado em OUTRA estação). O transporte (repasse de cookie/last-event-id,
// streaming do corpo, propagação de status) vive na layer operator-kit
// (server/utils/eventStream.ts, auto-importado). Ver ADR-016.
export default defineEventHandler((event) => proxyEventStream(event, "/events/cash/"));
