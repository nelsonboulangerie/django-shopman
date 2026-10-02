import type { ProductOptionGroup, ProductOptionSelection } from '~/types/shopman'
import { formatCentavos } from '~/presentation/cart'

// Escolhas no produto (Fase 1): transforms puros da folha de opções. A seleção é
// um mapa grupo → refs escolhidas, na ordem do toque. O servidor relê tudo do
// catálogo; aqui só se decide o que a tela mostra e o que a loja manda.

export type OptionSelectionState = Record<string, string[]>

export function hasOptionGroups (groups: ProductOptionGroup[] | null | undefined): boolean {
  return Array.isArray(groups) && groups.length > 0
}

/** Escolha única: o grupo pede exatamente uma opção. */
export function isSingleChoice (group: Pick<ProductOptionGroup, 'min' | 'max'>): boolean {
  return group.max === 1 && group.min === 1
}

/** A regra do grupo em uma frase curta: "Escolha 1", "Opcional", "Opcional, até 2". */
export function optionGroupRule (group: Pick<ProductOptionGroup, 'min' | 'max'>): string {
  const { min, max } = group
  if (min <= 0) return max <= 1 ? 'Opcional' : `Opcional, até ${max}`
  if (min === max) return `Escolha ${min}`
  return `Escolha de ${min} a ${max}`
}

function selectedIn (state: OptionSelectionState, groupRef: string): string[] {
  return state[groupRef] || []
}

/**
 * Toque numa opção. Escolhida: sai. Não escolhida: entra, respeitando o teto.
 * No grupo de teto 1 a nova toma o lugar da anterior (é o gesto do rádio);
 * acima disso, no teto, o toque não faz nada (a opção aparece desabilitada).
 */
export function toggleOption (
  state: OptionSelectionState,
  group: ProductOptionGroup,
  optionRef: string
): OptionSelectionState {
  const option = group.options.find(candidate => candidate.ref === optionRef)
  if (!option) return state
  const current = selectedIn(state, group.ref)
  if (current.includes(optionRef)) {
    // Escolha única obrigatória não se desmarca tocando de novo.
    if (isSingleChoice(group)) return state
    return { ...state, [group.ref]: current.filter(ref => ref !== optionRef) }
  }
  if (!option.available) return state
  if (group.max <= 1) return { ...state, [group.ref]: [optionRef] }
  if (current.length >= group.max) return state
  return { ...state, [group.ref]: [...current, optionRef] }
}

export function isOptionSelected (state: OptionSelectionState, groupRef: string, optionRef: string): boolean {
  return selectedIn(state, groupRef).includes(optionRef)
}

/** A opção está travada: fora hoje, ou o grupo já chegou ao teto (e ela não está nele). */
export function isOptionLocked (
  state: OptionSelectionState,
  group: ProductOptionGroup,
  optionRef: string
): boolean {
  const option = group.options.find(candidate => candidate.ref === optionRef)
  if (!option) return true
  const current = selectedIn(state, group.ref)
  if (current.includes(optionRef)) return false
  if (!option.available) return true
  return group.max > 1 && current.length >= group.max
}

/** Quantas faltam no grupo para cumprir o mínimo (0 = cumprido). */
export function optionsMissing (state: OptionSelectionState, group: ProductOptionGroup): number {
  return Math.max(0, group.min - selectedIn(state, group.ref).length)
}

export function optionsSelectionValid (state: OptionSelectionState, groups: ProductOptionGroup[]): boolean {
  return groups.every(group => {
    const chosen = selectedIn(state, group.ref)
    if (chosen.length < group.min || chosen.length > group.max) return false
    return chosen.every(ref => group.options.some(option => option.ref === ref && option.available))
  })
}

/** Preço de uma unidade: o do produto mais as opções escolhidas. */
export function optionsTotalQ (basePriceQ: number, state: OptionSelectionState, groups: ProductOptionGroup[]): number {
  let total = basePriceQ
  for (const group of groups) {
    for (const ref of selectedIn(state, group.ref)) {
      const option = group.options.find(candidate => candidate.ref === ref)
      if (option) total += Math.max(0, option.price_q)
    }
  }
  return total
}

/** "+ R$ 4,00" quando a opção custa; '' quando não muda o preço. */
export function optionPriceLabel (priceQ: number): string {
  return priceQ > 0 ? `+ ${formatCentavos(priceQ)}` : ''
}

/** O que a loja manda: só `{group, ref}`, na ordem dos grupos do catálogo. */
export function optionsPayload (state: OptionSelectionState, groups: ProductOptionGroup[]): ProductOptionSelection[] {
  return groups.flatMap(group => selectedIn(state, group.ref)
    .filter(ref => group.options.some(option => option.ref === ref))
    .map(ref => ({ group: group.ref, ref })))
}

/**
 * Seleção inicial: o grupo obrigatório de escolha única com UMA opção disponível
 * já nasce escolhido (não há o que decidir). O resto nasce vazio.
 */
export function initialOptionsState (groups: ProductOptionGroup[]): OptionSelectionState {
  const state: OptionSelectionState = {}
  for (const group of groups) {
    const available = group.options.filter(option => option.available)
    state[group.ref] = isSingleChoice(group) && available.length === 1 ? [available[0]!.ref] : []
  }
  return state
}

/** Primeira pendência, para o rodapé dizer o que falta: "Escolha 1 em Sabor". */
export function firstMissingOptionHint (state: OptionSelectionState, groups: ProductOptionGroup[]): string {
  for (const group of groups) {
    const missing = optionsMissing(state, group)
    if (missing > 0) return `Escolha ${missing} em ${group.label}`
  }
  return ''
}
