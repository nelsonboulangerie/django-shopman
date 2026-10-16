// Rota SSE same-origin do painel de retirada do cliente: /sse/pickup →
// streaming do canal PÚBLICO `pickup-board` do Django, que mora ao lado do GET
// que ele avisa (/api/v1/backstage/kds/pickup/events/). A TV abre sem sessão de
// operador, e o canal não pede uma: o corpo é vazio, o painel refaz o GET.
// Transporte na layer operator-kit (server/utils/eventStream.ts, auto-importado).
export default defineEventHandler((event) =>
  proxyEventStream(event, "/api/v1/backstage/kds/pickup/events/"),
);
