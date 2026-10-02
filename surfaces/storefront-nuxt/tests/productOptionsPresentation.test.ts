// Escolhas no produto (Fase 1): regras puras da folha de opções. O Frappé tem
// "Sabor" (escolha 1, sem acréscimo); o Croque tem "Adicionais" (opcional, até 2,
// com preço). A loja manda só {group, ref}; o preço exibido soma as escolhas.
import { describe, expect, it } from 'vitest'
import {
  firstMissingOptionHint,
  hasOptionGroups,
  initialOptionsState,
  isOptionLocked,
  optionGroupRule,
  optionPriceLabel,
  optionsPayload,
  optionsSelectionValid,
  optionsTotalQ,
  toggleOption
} from '~/presentation/productOptions'
import type { ProductOptionGroup } from '~/types/shopman'

const sabor: ProductOptionGroup = {
  ref: 'sabor',
  label: 'Sabor',
  min: 1,
  max: 1,
  options: [
    { ref: 'cafe', label: 'Café', price_q: 0, available: true },
    { ref: 'chocolate', label: 'Chocolate', price_q: 0, available: true },
    { ref: 'frutas', label: 'Frutas vermelhas', price_q: 0, available: false }
  ]
}

const adicionais: ProductOptionGroup = {
  ref: 'adicionais',
  label: 'Adicionais',
  min: 0,
  max: 2,
  options: [
    { ref: 'ovo', label: 'Ovo frito', price_q: 400, available: true },
    { ref: 'salada', label: 'Salada', price_q: 300, available: true },
    { ref: 'bacon', label: 'Bacon', price_q: 500, available: true },
    { ref: 'queijo', label: 'Queijo extra', price_q: 350, available: false }
  ]
}

describe('regra legível do grupo', () => {
  it('diz o mínimo e o teto em palavras', () => {
    expect(optionGroupRule({ min: 1, max: 1 })).toBe('Escolha 1')
    expect(optionGroupRule({ min: 2, max: 2 })).toBe('Escolha 2')
    expect(optionGroupRule({ min: 1, max: 3 })).toBe('Escolha de 1 a 3')
    expect(optionGroupRule({ min: 0, max: 1 })).toBe('Opcional')
    expect(optionGroupRule({ min: 0, max: 2 })).toBe('Opcional, até 2')
  })

  it('nenhuma regra usa travessão', () => {
    for (const rule of [optionGroupRule(sabor), optionGroupRule(adicionais), optionPriceLabel(400)]) {
      expect(rule).not.toMatch(/[—–]/)
    }
  })
})

describe('toggleOption', () => {
  it('escolha única troca a anterior e não se desmarca tocando de novo', () => {
    let state = initialOptionsState([sabor])
    state = toggleOption(state, sabor, 'cafe')
    expect(state.sabor).toEqual(['cafe'])
    state = toggleOption(state, sabor, 'chocolate')
    expect(state.sabor).toEqual(['chocolate'])
    state = toggleOption(state, sabor, 'chocolate')
    expect(state.sabor).toEqual(['chocolate'])
  })

  it('opção indisponível não entra', () => {
    const state = toggleOption(initialOptionsState([sabor]), sabor, 'frutas')
    expect(state.sabor).toEqual([])
    expect(isOptionLocked(state, sabor, 'frutas')).toBe(true)
  })

  it('múltipla respeita o teto e trava as demais quando chega nele', () => {
    let state = initialOptionsState([adicionais])
    state = toggleOption(state, adicionais, 'ovo')
    state = toggleOption(state, adicionais, 'salada')
    state = toggleOption(state, adicionais, 'bacon')
    expect(state.adicionais).toEqual(['ovo', 'salada'])
    expect(isOptionLocked(state, adicionais, 'bacon')).toBe(true)
    expect(isOptionLocked(state, adicionais, 'ovo')).toBe(false)
    state = toggleOption(state, adicionais, 'ovo')
    expect(state.adicionais).toEqual(['salada'])
    expect(isOptionLocked(state, adicionais, 'bacon')).toBe(false)
  })

  it('opcional de teto 1 desmarca tocando de novo', () => {
    const group = { ...adicionais, max: 1 }
    let state = toggleOption(initialOptionsState([group]), group, 'ovo')
    state = toggleOption(state, group, 'salada')
    expect(state.adicionais).toEqual(['salada'])
    state = toggleOption(state, group, 'salada')
    expect(state.adicionais).toEqual([])
  })
})

describe('validade, preço e payload', () => {
  it('só é válido com os mínimos cumpridos', () => {
    const groups = [sabor, adicionais]
    let state = initialOptionsState(groups)
    expect(optionsSelectionValid(state, groups)).toBe(false)
    expect(firstMissingOptionHint(state, groups)).toBe('Escolha 1 em Sabor')
    state = toggleOption(state, sabor, 'cafe')
    expect(optionsSelectionValid(state, groups)).toBe(true)
    expect(firstMissingOptionHint(state, groups)).toBe('')
  })

  it('opcional sem nada escolhido é válido', () => {
    expect(optionsSelectionValid(initialOptionsState([adicionais]), [adicionais])).toBe(true)
  })

  it('seleção com opção indisponível não vale', () => {
    expect(optionsSelectionValid({ sabor: ['frutas'] }, [sabor])).toBe(false)
  })

  it('escolha única obrigatória com uma opção disponível nasce escolhida', () => {
    const one = { ...sabor, options: [sabor.options[0]!, { ...sabor.options[1]!, available: false }] }
    expect(initialOptionsState([one]).sabor).toEqual(['cafe'])
    expect(initialOptionsState([sabor]).sabor).toEqual([])
  })

  it('preço = produto + opções escolhidas', () => {
    const state = { sabor: ['cafe'], adicionais: ['ovo', 'salada'] }
    expect(optionsTotalQ(3200, state, [sabor, adicionais])).toBe(3900)
    expect(optionsTotalQ(3200, {}, [sabor, adicionais])).toBe(3200)
  })

  it('preço da opção aparece só quando custa', () => {
    expect(optionPriceLabel(400)).toBe('+ R$ 4,00')
    expect(optionPriceLabel(0)).toBe('')
  })

  it('payload leva só {group, ref}, na ordem dos grupos', () => {
    const state = { adicionais: ['salada', 'ovo'], sabor: ['chocolate'] }
    expect(optionsPayload(state, [sabor, adicionais])).toEqual([
      { group: 'sabor', ref: 'chocolate' },
      { group: 'adicionais', ref: 'salada' },
      { group: 'adicionais', ref: 'ovo' }
    ])
  })

  it('hasOptionGroups trata ausente e vazio como sem escolhas', () => {
    expect(hasOptionGroups(undefined)).toBe(false)
    expect(hasOptionGroups([])).toBe(false)
    expect(hasOptionGroups([sabor])).toBe(true)
  })
})
