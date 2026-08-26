// A PRIMEIRA PERGUNTA DO ATENDIMENTO — "é pra comer aqui ou pra levar?".
//
// Recebimento decide taxa, janela de horário e endereço, e decide também se vale
// a pena pedir o telefone. Perguntado no fim, tudo isso chega depois de o preço
// já ter sido dito em voz alta.
//
// A regra de QUANDO perguntar mora aqui, fora da página, porque ela tem quatro
// condições e um estado por comanda — é o tipo de coisa que se quebra sem
// ninguém notar quando vive solta dentro de um `v-if`.

export interface FulfillmentPromptState {
  /** Estamos na tela de venda (não no quadro de comandas). */
  inSaleView: boolean;
  /** Estamos no checkout (a pergunta é do começo, não do fim). */
  checkoutMode: boolean;
  hasOpenTab: boolean;
  /** Quantos itens já foram lançados nesta comanda. */
  itemCount: number;
  /** A comanda em que a pergunta já foi feita (ou dispensada). */
  askedFor: string;
  tabSessionKey: string;
}

/**
 * Perguntar agora?
 *
 * Só numa comanda ABERTA e VAZIA, na tela de venda, e uma vez por comanda.
 *
 * O `itemCount` é o que faz a faixa sumir sozinha: quem já começou a lançar
 * produto respondeu "retirada" com o corpo, e insistir na pergunta depois disso
 * é interromper alguém que já está trabalhando.
 */
export function shouldAskFulfillment(state: FulfillmentPromptState): boolean {
  if (!state.inSaleView || state.checkoutMode) return false;
  if (!state.hasOpenTab) return false;
  if (state.itemCount > 0) return false;
  return state.askedFor !== state.tabSessionKey;
}

/**
 * A marca de "já perguntei", por comanda.
 *
 * Sem comanda o valor cai num sentinela que nunca é uma `session_key` real —
 * marcar com string vazia faria a pergunta ficar respondida para a PRÓXIMA
 * comanda também, já que ela nasce sem chave por um instante.
 */
export function askedMarkFor(tabSessionKey: string): string {
  return tabSessionKey || "-";
}
