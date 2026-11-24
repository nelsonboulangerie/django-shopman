import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'
import { orderAccessErrorView } from '~/presentation/orderAccess'
import { safeInternalPath } from '~/utils/safeNavigation'

describe('order access error view', () => {
  it('treats 404/403 as "needs login", not a dead error', () => {
    for (const code of [404, 403]) {
      const v = orderAccessErrorView(code, 'payment')
      expect(v.showLogin).toBe(true)
      expect(v.canRetry).toBe(false)
      expect(v.title).toBe('Não encontramos este pagamento')
      expect(v.message).toMatch(/Entre com seu telefone/)
    }
    expect(orderAccessErrorView(404, 'tracking').title).toBe('Não encontramos este pedido')
  })

  it('treats 429 as a calm wait-and-retry', () => {
    const v = orderAccessErrorView(429, 'tracking')
    expect(v.showLogin).toBe(false)
    expect(v.canRetry).toBe(true)
    expect(v.title).toMatch(/Muitas atualizações/)
  })

  it('falls back to a retryable instability message', () => {
    const v = orderAccessErrorView(500, 'payment')
    expect(v.showLogin).toBe(false)
    expect(v.canRetry).toBe(true)
    expect(v.title).toBe('Não foi possível abrir o pagamento agora')
    const t = orderAccessErrorView(undefined, 'tracking')
    expect(t.canRetry).toBe(true)
    expect(t.title).toBe('Não foi possível carregar o acompanhamento agora')
  })
})

// OC-01 (decisão D5 do dono): o aviso de pedido leva só o link COMUM `/pedido/<ref>`,
// sem credencial. Em outro dispositivo, sem sessão, a página do pedido recebe 404 do
// Django e tem de levar à entrada com o pedido como destino, e a entrada tem de voltar
// para ele (por código, dispositivo confiável ou mensagem do WhatsApp). O lado Django
// está em `shopman/storefront/tests/security/test_aviso_de_pedido_sem_credencial.py`.
describe('link comum do aviso: /pedido/<ref> sem sessão leva à entrada e volta ao pedido', () => {
  const read = (path: string) => readFileSync(resolve(__dirname, '..', path), 'utf8')

  it('a página do pedido manda "Entrar" para /entrar com o pedido no next', () => {
    const page = read('app/pages/pedido/[ref]/index.vue')
    expect(page).toContain("orderAccessErrorView((error.value as { statusCode?: number } | null)?.statusCode, 'tracking')")
    expect(page).toContain('const loginHref = computed(() => `/entrar?next=${encodeURIComponent(`/pedido/${orderRef.value}`)}`)')
    expect(page).toContain('<UiButton v-if="errorView.showLogin" :to="loginHref"')
    expect(orderAccessErrorView(404, 'tracking').showLogin).toBe(true)
  })

  it('a entrada aceita /pedido/<ref> como destino e volta para ele', () => {
    expect(safeInternalPath('/pedido/ORD-1')).toBe('/pedido/ORD-1')

    const login = read('app/pages/entrar.vue')
    expect(login).toContain('const nextUrl = computed(() => safeInternalPath(route.query.next))')
    // Pelo WhatsApp: o destino viaja no código NB e volta na troca do link.
    expect(login).toContain('waStart(nextUrl.value)')
    // Por código ou dispositivo confiável: a página navega ao destino depois de entrar.
    expect(login).toContain('await navigateTo(nextUrl.value)')
  })
})
