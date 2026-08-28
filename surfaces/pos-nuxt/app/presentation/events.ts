// Decisão pura do tempo real do PDV (testável sem browser).
//
// O canal /sse/cash carrega SINAL, não estado (ADR-016): qualquer evento pede o
// mesmo refetch da Projection do terminal, então não há filtro por payload — a
// única decisão de verdade é a do fallback: quando o tick de poll deve rodar.

export type PosRealtimeState = "connecting" | "live" | "polling";

/**
 * O poll é FALLBACK em cadência calma, não um segundo canal: com o SSE vivo, o
 * tick não refaz nada (o push já refez). Ele só carrega a tela quando o stream
 * não está de pé — proxy sem streaming, 403 na conexão, rede que caiu.
 */
export function shouldPollTick(state: PosRealtimeState): boolean {
  return state !== "live";
}

/**
 * O SSE so faz sentido com a estacao identificada e desbloqueada: no gate
 * (login/lock) os canais sao negados e o EventSource entra no ciclo de
 * reconexao com 400. Enquanto desabilitado, o poll de fallback segue sendo a
 * fonte calma da tela.
 */
export function shouldConnectSse(enabled: boolean | undefined): boolean {
  return enabled !== false;
}
