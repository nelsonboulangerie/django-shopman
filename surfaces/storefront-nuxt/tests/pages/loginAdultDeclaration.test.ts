import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import LoginPage from '~/pages/entrar.vue'
import AccessLinkPage from '~/pages/a.vue'
import { LOGIN_ADULT_DECLARATION } from '~/presentation/auth'

// A declaração de maioridade é feita ao ENTRAR. O que só a PÁGINA prova, e por
// isso se monta a tela: a frase aparece em todo passo de entrada (telefone,
// código; o aparelho reconhecido passa pelos mesmos passos) e na aterrissagem
// do access link — e some no gate de boas-vindas, que já é pós-autenticação.
// Nunca "18", "anos" nem "adulto" na tela de entrada.

const { fetchMock, navigate } = vi.hoisted(() => ({ fetchMock: vi.fn(), navigate: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('navigateTo', () => navigate)

function routeFetch (url: string, options?: { method?: string }) {
  const path = String(url)
  if (path.endsWith('/api/v1/storefront/home/')) return Promise.resolve(null)
  if (path.endsWith('/api/auth/device-check/')) return Promise.resolve({ ok: true, trusted: false, phone: '+5543999998888' })
  if (path.endsWith('/api/auth/request-code/')) {
    return Promise.resolve({ ok: true, phone: '+5543999998888', delivery_method: 'sms', delivery_label: 'SMS', dev_console_hint: false })
  }
  // O access link fica "Entrando…" enquanto o servidor não responde: é o
  // estado em que a pessoa lê a nota.
  if (path.endsWith('/api/auth/access/')) return new Promise(() => {})
  void options
  return Promise.resolve({})
}

const mounted: Array<{ unmount: () => void }> = []

function declaration (page: any) {
  return page.find('[data-login-adult-declaration]')
}

function expectDeclaration (page: any) {
  const note = declaration(page)
  expect(note.exists()).toBe(true)
  expect(note.text().replace(/\s+/g, ' ').trim()).toBe(LOGIN_ADULT_DECLARATION)
  expect(note.find('a').attributes('href')).toBe('/terms')
}

describe('login — a declaração de maioridade em toda porta de entrada', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    fetchMock.mockReset()
    fetchMock.mockImplementation(routeFetch)
    navigate.mockReset()
    useShopSession().reset()
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
  })

  it('shows the sentence, with the Terms link, on the phone step', async () => {
    const page = await mountSuspended(LoginPage, { route: '/entrar' })
    mounted.push(page)
    await flushPromises()

    expectDeclaration(page)
    expect(page.text()).not.toMatch(/\b18\b|anos|adult/i)
  })

  it('keeps the sentence on the code step', async () => {
    const page = await mountSuspended(LoginPage, { route: '/entrar' })
    mounted.push(page)
    await flushPromises()

    const other = page.findAll('button').find((b: any) => b.text().includes('Não consigo usar WhatsApp'))!
    await other.trigger('click')
    await flushPromises()
    await page.find('#login-phone').setValue('43999998888')
    await page.find('form').trigger('submit')
    await flushPromises()

    expect(page.text()).toContain('Código enviado')
    expectDeclaration(page)
  })

  it('shows the sentence while the access link is being exchanged', async () => {
    const page = await mountSuspended(AccessLinkPage, { route: '/a?t=token-de-teste' })
    mounted.push(page)
    await flushPromises()

    expect(page.text()).toContain('Entrando na sua conta')
    expectDeclaration(page)
  })

  it('does not repeat it on the welcome gate — the person already entered', async () => {
    const session = useShopSession()
    session.setFromAuthSession({
      is_authenticated: true,
      customer_name: '',
      requires_welcome: true,
      welcome_asks_name: true,
      welcome_asks_marketing: false,
      welcome_suggested_name: ''
    })
    const page = await mountSuspended(LoginPage, { route: '/entrar?welcome=1&next=%2Fconta' })
    mounted.push(page)
    await flushPromises()

    expect(page.find('form[data-login-welcome]').exists()).toBe(true)
    expect(declaration(page).exists()).toBe(false)
  })
})
