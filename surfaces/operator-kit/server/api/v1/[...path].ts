// BFF canônico das oito superfícies de operador: `/api/v1/**` do app vai para o
// Django com cookie, CSRF e cabeçalhos tratados no transporte da layer
// (server/utils/djangoProxy.ts, auto-importado). Antes esta casca de quatro linhas
// era copiada em cada app; a rota vive aqui e chega a todos por `extends`, como já
// acontece com /health/* e /sse/notifications.
//
// O storefront NÃO estende esta layer (superfície de cliente, proxy e CSRF próprios)
// e mantém o seu `server/api/v1/[...path].ts`.
export default defineEventHandler((event) => {
  const rawPath = event.context.params?.path || "";
  const path = Array.isArray(rawPath) ? rawPath.join("/") : rawPath;
  return proxyDjangoApi(event, path);
});
