import type { OrderingProjection } from '~/types/shopman'

// O topo da home diz o estado da casa E o que dá para fazer, e o "o que dá para
// fazer" sai de `home.ordering` (OC-04), o resumo das MESMAS promessas que os
// cards do cardápio dizem. Era uma constante: às 22h, com 0 de 31 itens podendo
// ir à sacola, a home dizia "Você já pode finalizar o pedido" (laudo da Etapa II,
// U1). Com a casa fechada, a finalização aceita pedido e pagamento e a casa
// confere na abertura (ADR-036); a frase usa o mesmo vocabulário do pagamento
// fora do horário ("conferimos quando abrirmos").

// Algo tem horário hoje (a casa ainda abre hoje): dá para finalizar já.
export const CLOSED_HERO_HINT = 'Você já pode finalizar o pedido, e conferimos quando abrirmos.'

// Nada do cardápio pode ir à sacola: diz isso e aponta o caminho que existe, o
// "Me avise" de cada item. Nunca promete finalização.
export const NO_ORDERING_HINT = 'Hoje não há encomenda aberta. No cardápio, toque em “Me avise” no item que você quer.'

// O primeiro horário é de outro dia: a frase diz qual ("amanhã, terça").
export function preorderHint (dayLabel: string): string {
  return `Você já pode encomendar para ${dayLabel}. Conferimos o pedido quando abrirmos.`
}

function orderingHint (ordering: OrderingProjection | null | undefined, statusOpen: boolean): string {
  if (!ordering) return ''
  if (ordering.state === 'none') return NO_ORDERING_HINT
  if (statusOpen) return ''
  if (ordering.state === 'preorder' && ordering.day_label.trim()) return preorderHint(ordering.day_label.trim())
  return CLOSED_HERO_HINT
}

/**
 * A linha acima do título do hero, ou `undefined` quando não há o que dizer.
 *
 * Casa fechada: o estado ("Fechado agora. Abrimos amanhã às 9h") seguido do que
 * dá para fazer, pelo `ordering`. Casa aberta: só quando nada pode ser pedido.
 * Sem `ordering` (resposta sem o campo), só o estado: a frase nunca promete o
 * que a projeção não confirmou.
 */
export function heroEyebrow (input: {
  statusOpen: boolean
  statusLabel?: string | null
  ordering?: OrderingProjection | null
}): string | undefined {
  const hint = orderingHint(input.ordering, input.statusOpen)
  if (input.statusOpen) return hint || undefined
  const label = input.statusLabel?.trim().replace(/\.+$/, '')
  const parts = [label ? `${label}.` : '', hint].filter(Boolean)
  return parts.length ? parts.join(' ') : undefined
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
