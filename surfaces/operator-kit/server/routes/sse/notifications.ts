// Rota SSE same-origin do canal PESSOAL: /sse/notifications →
// streaming do eventstream do Django (/events/me/, canal `user-<id>`).
// Na layer: os oito apps de operador herdam a rota sem copiá-la.
//
// O Django resolve o dono do canal pela sessão — o id do usuário nunca vem do
// cliente, então ninguém escuta a caixa alheia trocando um parâmetro.
export default defineEventHandler((event) => proxyEventStream(event, "/events/me/"));
