// Decisões puras da troca de versão do app instalado da loja (porte do
// `operator-kit/tests/pwaRuntime.test.ts`, só com a metade "sonda" e o aviso).
import { describe, expect, it } from 'vitest'
import {
  PWA_UPDATE_CHECK_FLOOR_MS,
  PWA_UPDATE_CHECK_MS,
  pwaUpdatePromptRouteExcluded,
  shouldCheckForUpdate,
  shouldShowPwaUpdatePrompt
} from '~/presentation/pwaRuntime'

describe('shouldCheckForUpdate', () => {
  it('sonda quando o piso entre chamadas passou', () => {
    const base = { lastCheckAt: 0, online: true, visible: true }
    expect(shouldCheckForUpdate({ ...base, now: PWA_UPDATE_CHECK_FLOOR_MS - 1 })).toBe(false)
    expect(shouldCheckForUpdate({ ...base, now: PWA_UPDATE_CHECK_FLOOR_MS })).toBe(true)
  })

  it('não sonda offline nem com a janela fora da vista', () => {
    const base = { now: 10_000_000, lastCheckAt: 0 }
    expect(shouldCheckForUpdate({ ...base, online: false, visible: true })).toBe(false)
    expect(shouldCheckForUpdate({ ...base, online: true, visible: false })).toBe(false)
  })

  it('relógio ajustado para trás não congela a sonda para sempre', () => {
    expect(shouldCheckForUpdate({ now: 1_000, lastCheckAt: 9_999_999, online: true, visible: true })).toBe(true)
  })

  it('a régua é a mesma do kit: 30 min de intervalo, 60 s de piso', () => {
    expect(PWA_UPDATE_CHECK_MS).toBe(30 * 60 * 1000)
    expect(PWA_UPDATE_CHECK_FLOOR_MS).toBe(60 * 1000)
  })
})

describe('pwaUpdatePromptRouteExcluded', () => {
  it('cala o aviso onde a recarga perderia algo em curso', () => {
    expect(pwaUpdatePromptRouteExcluded('/finalizar')).toBe(true)
    expect(pwaUpdatePromptRouteExcluded('/finalizar/pagamento')).toBe(true)
    expect(pwaUpdatePromptRouteExcluded('/pedido/ORD-1')).toBe(true)
    expect(pwaUpdatePromptRouteExcluded('/entrar')).toBe(true)
    expect(pwaUpdatePromptRouteExcluded('/a')).toBe(true)
  })

  it('mostra no resto da loja, inclusive na sacola e na conta', () => {
    for (const path of ['/', '/menu', '/sacola', '/produto/PAO', '/conta', '/conta/pedidos', '/busca']) {
      expect(pwaUpdatePromptRouteExcluded(path)).toBe(false)
    }
  })

  it('não confunde prefixo de palavra com prefixo de caminho', () => {
    expect(pwaUpdatePromptRouteExcluded('/finalizarx')).toBe(false)
    expect(pwaUpdatePromptRouteExcluded('/ajuda')).toBe(false)
    expect(pwaUpdatePromptRouteExcluded('/entrar-agora')).toBe(false)
  })
})

describe('shouldShowPwaUpdatePrompt', () => {
  const ready = { needsRefresh: true, online: true, path: '/menu' }

  it('aparece sempre que há versão nova e a tela permite', () => {
    expect(shouldShowPwaUpdatePrompt(ready)).toBe(true)
  })

  it('some sem versão nova, sem rede ou em tela calada', () => {
    expect(shouldShowPwaUpdatePrompt({ ...ready, needsRefresh: false })).toBe(false)
    expect(shouldShowPwaUpdatePrompt({ ...ready, online: false })).toBe(false)
    expect(shouldShowPwaUpdatePrompt({ ...ready, path: '/finalizar' })).toBe(false)
  })
})
