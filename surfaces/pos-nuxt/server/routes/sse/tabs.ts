// Rota SSE same-origin do PDV: /sse/tabs → streaming do eventstream do Django
// (canal /events/tabs/ — a COZINHA mexeu numa comanda deste balcão). O corpo é
// sinal mínimo: a chave da comanda e mais nada, porque quem recebe refaz o fetch
// canônico da Projection do terminal. Canal próprio, e não o `kds`, porque ali
// trafega o board inteiro da cozinha e quem opera o caixa não tem `operate_kds`.
// O transporte vive na layer operator-kit (server/utils/eventStream.ts). Ver ADR-016.
export default defineEventHandler((event) => proxyEventStream(event, "/events/tabs/"));
