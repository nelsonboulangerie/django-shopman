// Rota SSE same-origin do PDV: /sse/stock → streaming do eventstream do Django
// (`/events/stock/`, o canal `stock-<canal do PDV>`). O motor de disponibilidade
// avisa ali a cada reserva e movimento de estoque; o corpo é só o SKU, e quem
// recebe relê os selos da grade (`?only=availability`). Outro balcão vende a
// última unidade e o tile vira "Esgotado" sem ninguém tocar. A porta no Django
// exige a permissão do PDV. Transporte na layer operator-kit. Ver ADR-016.
export default defineEventHandler((event) => proxyEventStream(event, "/events/stock/"));
