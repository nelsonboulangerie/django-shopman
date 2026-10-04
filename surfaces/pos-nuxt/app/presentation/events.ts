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

/** O "ao vivo" discreto do cabeçalho (kit `OperatorLiveStatus`), lido do estado real. */
export interface PosLiveStatusView {
  tone: "live" | "calm" | "off";
  label: string;
  detail: string;
}

/**
 * Sem rede: vermelho, por extenso. Com o push vivo: só o ponto e a hora. Enquanto o
 * push não conecta, a tela segue certa pelo poll calmo de 60 s, e é isso que se diz.
 */
export function posLiveStatus(input: { online: boolean; realtime: PosRealtimeState }): PosLiveStatusView {
  if (!input.online) {
    return { tone: "off", label: "Sem conexão", detail: "A tela mostra a última leitura e volta sozinha quando a rede voltar" };
  }
  if (input.realtime === "live") {
    return { tone: "live", label: "Ao vivo", detail: "Mudanças de outras estações chegam na hora" };
  }
  return { tone: "calm", label: "Atualiza a cada 60 s", detail: "O tempo real ainda não conectou; a tela relê sozinha" };
}
