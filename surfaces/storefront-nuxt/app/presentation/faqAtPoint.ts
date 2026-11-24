// EXPERIMENT(duvida-no-ponto) remove_after 2027-02-20
// Arquivo inteiro da versão B do experimento `duvida-no-ponto` (OC-33 B3): a dúvida
// respondida onde ela aparece. B venceu: a lista da home sai e este arquivo fica sem a
// marca. B perdeu: este arquivo sai inteiro.
//
// Lógica pura: qual pergunta da FAQ mora em cada ponto da jornada. A pergunta e a
// resposta são as MESMAS da página /faq (`build_public_faq`, que chega no `shell.faq`);
// aqui só se escolhe quais, pela chave das respostas operacionais (`ref`), que vêm da
// configuração da loja. Nada aqui reclassifica estado nem promete nada (X2, X13).
import type { FAQItemProjection } from '~/types/shopman'

export type FaqPoint = 'cart'

/** Quantas perguntas cabem num ponto: uma linha de cada, recolhidas. */
export const FAQ_AT_POINT_LIMIT = 3

/**
 * As perguntas de cada ponto, na ordem em que aparecem. Pergunta que a loja não
 * responde (encomenda desligada no canal) simplesmente não vem no `shell.faq`, e o
 * ponto mostra as que sobram, ou nada.
 *
 * Nenhuma pergunta repete o que a tela já mostra (OC-31: sem resposta dupla). Por
 * isso o único ponto é a sacola: o pagamento não tem (as formas de pagamento estão
 * nas opções), nem o produto (o aviso de alérgenos já está em "Ingredientes e
 * restrições").
 */
export const FAQ_AT_POINT: Readonly<Record<FaqPoint, readonly string[]>> = {
  cart: ['delivery', 'hours', 'preorder']
}

export function faqAtPoint (
  items: FAQItemProjection[] | null | undefined,
  point: FaqPoint
): FAQItemProjection[] {
  const byRef = new Map<string, FAQItemProjection>()
  for (const item of items || []) {
    if (item?.ref && item.question?.trim() && item.answer?.trim() && !byRef.has(item.ref)) {
      byRef.set(item.ref, item)
    }
  }
  return FAQ_AT_POINT[point]
    .map(ref => byRef.get(ref))
    .filter((item): item is FAQItemProjection => !!item)
    .slice(0, FAQ_AT_POINT_LIMIT)
}
