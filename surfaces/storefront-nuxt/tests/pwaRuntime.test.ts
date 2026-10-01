// Decisões puras da troca de versão do app instalado da loja (porte do
// `operator-kit/tests/pwaRuntime.test.ts`, com a sonda e as duas portas que FORÇAM
// a versão nova, D9).
import { describe, expect, it } from 'vitest'
import {
  PWA_UPDATE_CHECK_FLOOR_MS,
  PWA_UPDATE_CHECK_MS,
  pwaUpdateRouteProtected,
  shouldApplyPwaUpdateOnNavigation,
  shouldBlockForPwaUpdate,
  shouldCheckForUpdate
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

describe('pwaUpdateRouteProtected', () => {
  it('protege checkout, pedido e login: ali a recarga perderia algo em curso', () => {
    expect(pwaUpdateRouteProtected('/finalizar')).toBe(true)
    expect(pwaUpdateRouteProtected('/finalizar/pagamento')).toBe(true)
    expect(pwaUpdateRouteProtected('/pedido/ORD-1')).toBe(true)
    expect(pwaUpdateRouteProtected('/entrar')).toBe(true)
    expect(pwaUpdateRouteProtected('/a')).toBe(true)
  })

  it('o resto da loja não é protegido, inclusive a sacola e a conta', () => {
    for (const path of ['/', '/menu', '/sacola', '/produto/PAO', '/conta', '/conta/pedidos', '/busca']) {
      expect(pwaUpdateRouteProtected(path)).toBe(false)
    }
  })

  it('não confunde prefixo de palavra com prefixo de caminho', () => {
    expect(pwaUpdateRouteProtected('/finalizarx')).toBe(false)
    expect(pwaUpdateRouteProtected('/ajuda')).toBe(false)
    expect(pwaUpdateRouteProtected('/entrar-agora')).toBe(false)
  })
})

describe('shouldBlockForPwaUpdate', () => {
  const ready = { needsRefresh: true, online: true, path: '/menu' }

  it('bloqueia sempre que há versão nova e a tela não é protegida', () => {
    expect(shouldBlockForPwaUpdate(ready)).toBe(true)
  })

  it('não bloqueia sem versão nova, sem rede ou em tela protegida', () => {
    expect(shouldBlockForPwaUpdate({ ...ready, needsRefresh: false })).toBe(false)
    expect(shouldBlockForPwaUpdate({ ...ready, online: false })).toBe(false)
    for (const path of ['/finalizar', '/pedido/ORD-1', '/entrar', '/a']) {
      expect(shouldBlockForPwaUpdate({ ...ready, path })).toBe(false)
    }
  })
})

describe('shouldApplyPwaUpdateOnNavigation', () => {
  const ready = { needsRefresh: true, online: true, from: '/menu', to: '/produto/PAO' }

  it('com versão nova, navegar fora das telas protegidas recarrega no destino', () => {
    expect(shouldApplyPwaUpdateOnNavigation(ready)).toBe(true)
    expect(shouldApplyPwaUpdateOnNavigation({ ...ready, from: '/', to: '/sacola' })).toBe(true)
  })

  it('nunca recarrega se a origem OU o destino for protegido', () => {
    for (const path of ['/finalizar', '/pedido/ORD-1', '/entrar', '/a']) {
      expect(shouldApplyPwaUpdateOnNavigation({ ...ready, to: path })).toBe(false)
      expect(shouldApplyPwaUpdateOnNavigation({ ...ready, from: path })).toBe(false)
    }
  })

  it('sem versão nova, sem rede ou sem troca de tela, não recarrega', () => {
    expect(shouldApplyPwaUpdateOnNavigation({ ...ready, needsRefresh: false })).toBe(false)
    expect(shouldApplyPwaUpdateOnNavigation({ ...ready, online: false })).toBe(false)
    expect(shouldApplyPwaUpdateOnNavigation({ ...ready, to: '/menu' })).toBe(false)
  })
})
