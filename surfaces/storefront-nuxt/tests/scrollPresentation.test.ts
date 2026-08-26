import { describe, expect, it } from 'vitest'
import { HEADER_COLLAPSE_AT, HEADER_EXPAND_AT, headerCollapsed } from '~/presentation/scroll'

describe('headerCollapsed', () => {
  it('expandida fica expandida até o limiar de colapso', () => {
    expect(headerCollapsed(false, 0)).toBe(false)
    expect(headerCollapsed(false, HEADER_EXPAND_AT)).toBe(false)
    expect(headerCollapsed(false, HEADER_COLLAPSE_AT)).toBe(false)
  })

  it('colapsa passado o limiar de colapso', () => {
    expect(headerCollapsed(false, HEADER_COLLAPSE_AT + 1)).toBe(true)
    expect(headerCollapsed(false, 400)).toBe(true)
  })

  it('colapsada fica colapsada na zona morta entre os limiares', () => {
    expect(headerCollapsed(true, HEADER_COLLAPSE_AT)).toBe(true)
    expect(headerCollapsed(true, 8)).toBe(true)
    expect(headerCollapsed(true, HEADER_EXPAND_AT)).toBe(true)
  })

  it('reexpande só de volta ao topo', () => {
    expect(headerCollapsed(true, HEADER_EXPAND_AT - 1)).toBe(false)
    expect(headerCollapsed(true, 0)).toBe(false)
  })

  it('regressão: o recuo causado pelo próprio colapso não reabre a barra', () => {
    // O laço original: rolagem parada em ~8px, colapsar encurtava a página, o
    // browser clampava o scroll para trás do limiar e a barra reabria — eterno.
    // Com histerese, o colapso em 25px seguido de recuo (clamp) mantém o estado.
    let collapsed = headerCollapsed(false, HEADER_COLLAPSE_AT + 1)
    expect(collapsed).toBe(true)
    collapsed = headerCollapsed(collapsed, 8)
    expect(collapsed).toBe(true)

    // E o clamp até o topo assenta expandida em um passo, sem voltar a colapsar.
    collapsed = headerCollapsed(collapsed, 0)
    expect(collapsed).toBe(false)
    expect(headerCollapsed(collapsed, 0)).toBe(false)
  })
})
