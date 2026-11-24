import type { OrderingProjection } from '~/types/shopman'

// O topo da home diz o que dá para fazer, e isso sai de `home.ordering` (OC-04),
// o resumo das MESMAS promessas que os cards do cardápio dizem. Era uma
// constante: às 22h, com 0 de 31 itens podendo ir à sacola, a home dizia "Você
// já pode finalizar o pedido" (laudo da Etapa II, U1). Com a casa fechada, o
// pedido entra e a casa confere na abertura (ADR-036).
//
// Curto de propósito (dono, prévia de 24/11: "MUUUITO prolixo"): a hora da
// abertura já está na faixa do topo, então aqui vai só "Fechado agora." e o
// que fazer.

// Algo tem horário hoje (a casa ainda abre hoje).
export const CLOSED_HERO_HINT = 'Já dá para pedir.'

// Nada do cardápio pode ir à sacola: diz isso e aponta o "Me avise" de cada
// item. Nunca promete finalização.
export const NO_ORDERING_HINT = 'Hoje não há encomenda aberta. Toque em “Me avise” no item.'

// O primeiro horário é de outro dia: a frase diz qual ("amanhã, terça").
export function preorderHint (dayLabel: string): string {
  return `Encomende para ${dayLabel}.`
}

function orderingHint (ordering: OrderingProjection, statusOpen: boolean): string {
  if (ordering.state === 'none') return NO_ORDERING_HINT
  if (statusOpen) return ''
  if (ordering.state === 'preorder' && ordering.day_label.trim()) return preorderHint(ordering.day_label.trim())
  return CLOSED_HERO_HINT
}

/**
 * A linha acima do título do hero, ou `undefined` quando não há o que dizer.
 *
 * Nada encomendável (aberta ou fechada): só isso e o "Me avise". Casa fechada
 * com o que pedir: a primeira frase do estado ("Fechado agora") e o que fazer.
 * Casa aberta com o que pedir: nada. Sem `ordering` (resposta sem o campo), só
 * o estado inteiro: a frase nunca promete o que a projeção não confirmou.
 */
export function heroEyebrow (input: {
  statusOpen: boolean
  statusLabel?: string | null
  ordering?: OrderingProjection | null
}): string | undefined {
  const label = input.statusLabel?.trim().replace(/\.+$/, '') || ''
  if (!input.ordering) {
    return input.statusOpen || !label ? undefined : `${label}.`
  }
  const hint = orderingHint(input.ordering, input.statusOpen)
  if (input.ordering.state === 'none' || input.statusOpen) return hint || undefined
  const state = label.split('. ')[0]?.trim()
  return state ? `${state}. ${hint}` : hint
}

/**
 * O rótulo do botão do hero com a casa fechada. "Fazer pedido" só quando há o
 * que pedir; com nada encomendável (ou sem o fato), o hero cai no "Ver cardápio"
 * da copy, que é onde está o "Me avise".
 */
export function closedHeroCtaLabel (ordering?: OrderingProjection | null): string | undefined {
  if (!ordering || ordering.state === 'none') return undefined
  return 'Fazer pedido'
}
