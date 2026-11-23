// Decisão pura do tempo real do PDV (testável sem browser).
//
// Os canais carregam SINAL, não estado (ADR-016): o evento só diz que mudou, e a
// tela refaz o fetch canônico. As decisões de verdade são o que reler (o escopo
// por canal) e quando o tick de poll de fallback deve rodar.

export type PosRealtimeState = "connecting" | "live" | "polling";

export type PosRefreshScope = "tabs" | "availability" | "all";

/** No canal de estoque, os avisos que mudam QUEM está na grade, não o selo: produto
 *  pausado ou despausado, e mutação do canal (#2586). Pedem a releitura inteira. */
const STOCK_WHOLE_READ_EVENTS = new Set(["product-paused", "listing-changed"]);

/**
 * O que reler quando um stream avisa. O aviso de COMANDA (`/sse/tabs`) muda só o
 * quadro de comandas, e chega a todas as estações a cada salvar de qualquer
 * balcão: reler a projeção inteira nele enchia o servidor. O aviso de ESTOQUE
 * (`/sse/stock`) muda só os selos da grade ("Esgotado", "Sem caixa"), e chega a
 * cada venda, reserva e lote; produto pausado e mutação do canal, no mesmo stream,
 * mudam quem está na grade e relêem tudo. O resto (caixa, poll, volta à aba) relê tudo.
 */
export function refreshScopeForChannel(path: string | undefined, event?: string): PosRefreshScope {
  if (path === "/sse/tabs") return "tabs";
  if (path === "/sse/stock") return event && STOCK_WHOLE_READ_EVENTS.has(event) ? "all" : "availability";
  return "all";
}

/** Um selo da grade, como `?only=availability` devolve. */
export interface PosAvailabilityEntry {
  sku: string;
  sold_out: boolean;
  sold_out_reason: string;
  /** Unidades que restam hoje (#2610); ausente ou `null` = o tile não diz número. */
  units_left?: number | null;
}

/**
 * Encaixa os selos novos nos produtos da leitura atual, sem tocar no resto do
 * tile (preço, coleção, escolhas). Devolve a MESMA lista quando nenhum selo
 * mudou: a grade não redesenha a cada aviso de estoque que não a afeta. O SKU
 * que a leitura atual não tem fica de fora (sem preço, não está na grade).
 */
export function mergeAvailability<T extends { sku: string; sold_out?: boolean; sold_out_reason?: string; units_left?: number | null }>(
  products: readonly T[],
  entries: readonly PosAvailabilityEntry[],
): readonly T[] {
  const bySku = new Map(entries.map((entry) => [entry.sku, entry]));
  let changed = false;
  const next = products.map((product) => {
    const entry = bySku.get(product.sku);
    if (!entry) return product;
    const soldOut = Boolean(entry.sold_out);
    const reason = entry.sold_out_reason || "";
    // O saldo em número vem no MESMO aviso de estoque que o selo (#2610): a venda
    // de outro balcão baixa o "Restam 3" para "Restam 2" sem ninguém tocar.
    const left = entry.units_left ?? null;
    if (
      Boolean(product.sold_out) === soldOut
      && (product.sold_out_reason || "") === reason
      && (product.units_left ?? null) === left
    ) return product;
    changed = true;
    return { ...product, sold_out: soldOut, sold_out_reason: reason, units_left: left };
  });
  return changed ? next : products;
}

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
  tone: "live" | "calm";
  label: string;
  /** O curto do selo quando a barra aperta (kit `OperatorLiveStatus`, degrau 2). */
  shortLabel?: string;
  detail: string;
}

/**
 * Com o push vivo: só o ponto e a hora. Enquanto o push não conecta, a tela segue
 * certa pelo poll calmo de 60 s, e é isso que se diz. SEM REDE O SELO SAI (`null`):
 * quem diz o estado é a faixa "Sem conexão" do kit, no topo de toda tela. O selo
 * repetia a faixa, e com o aviso da tela o PDV dizia "Sem conexão" três vezes
 * (WP-PDV-SEM-CONEXAO, 10/10/2026).
 */
export function posLiveStatus(input: { online: boolean; realtime: PosRealtimeState }): PosLiveStatusView | null {
  if (!input.online) return null;
  if (input.realtime === "live") {
    return { tone: "live", label: "Ao vivo", detail: "Mudanças de outras estações chegam na hora" };
  }
  return { tone: "calm", label: "Atualiza sozinho a cada 60 s", shortLabel: "A cada 60 s", detail: "O tempo real ainda não conectou; a tela relê sozinha" };
}
