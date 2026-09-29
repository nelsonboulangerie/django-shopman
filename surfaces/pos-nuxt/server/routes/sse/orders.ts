// Rota SSE same-origin do PDV: /sse/orders → streaming do eventstream do Django
// (canal /events/orders/ — o MESMO do Gestor: pedido nasceu, mudou de status, foi
// pago). Quem assina são as Encomendas (o selo da barra lateral e as listas), que
// refazem a leitura canônica no evento (ADR-016). O corpo é ref+status, e o canal
// exige `shop.manage_orders` — a mesma régua da rota das Encomendas. O transporte
// vive na layer operator-kit (server/utils/eventStream.ts).
export default defineEventHandler((event) => proxyEventStream(event, "/events/orders/"));
