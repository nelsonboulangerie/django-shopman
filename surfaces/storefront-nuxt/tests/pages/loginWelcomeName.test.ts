import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import LoginPage from '~/pages/entrar.vue'

// O gate de boas-vindas do login é SÓ o nome. O que só a PÁGINA decide, e por
// isso se monta a tela:
//
// - o passo mostra título, campo e "Continuar" — e nenhum bloco de novidades
//   (a pergunta virou sheet na página de destino: MarketingPromptSheet);
// - "Continuar" = PATCH do perfil com o nome, e só; "Deixar para depois" segue
//   sem gravar; nenhum dos dois fala com `account/marketing-prompt/`;
// - cada passo (telefone, código, nome) é o foco da página pelo mecanismo
//   canônico (`useNextFocus`): o bloco do passo — que carrega o TÍTULO — vai à
//   linha de foco, e o primeiro campo recebe o foco SEM rolar. No celular,
//   `focus()` sem isso abria o teclado e o navegador rolava o campo até a borda,
//   deixando o título fora da tela ("meio rolada").

const { fetchMock, navigate } = vi.hoisted(() => ({ fetchMock: vi.fn(), navigate: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('navigateTo', () => navigate)

function routeFetch (url: string, options?: { method?: string }) {
  const path = String(url)
  const method = (options?.method || 'GET').toUpperCase()
  if (path.endsWith('/api/v1/storefront/home/')) return Promise.resolve(null)
  if (path.endsWith('/api/v1/account/profile/') && method === 'GET') return Promise.resolve({ first_name: '', birthday: '' })
  if (path.endsWith('/api/auth/device-check/')) return Promise.resolve({ ok: true, trusted: false, phone: '+5543999998888' })
  if (path.endsWith('/api/auth/request-code/')) {
    return Promise.resolve({ ok: true, phone: '+5543999998888', delivery_method: 'sms', delivery_label: 'SMS', dev_console_hint: false })
  }
  return Promise.resolve({})
}

function callsTo (suffix: string) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(suffix))
}

const mounted: Array<{ unmount: () => void }> = []
// Fronteira com o browser, espionada como no teste do próprio mecanismo
// (tests/composables/useNextFocus.test.ts): quem rolou até onde, e quem recebeu
// o foco com quais opções.
let scrolled: ReturnType<typeof vi.fn>
let focused: ReturnType<typeof vi.spyOn>
const nativeScrollIntoView = Element.prototype.scrollIntoView

function lastScroll () {
  const call = scrolled.mock.calls.at(-1)
  return call ? { element: scrolled.mock.contexts.at(-1) as HTMLElement, options: call[0] as ScrollIntoViewOptions } : null
}

function lastFocus () {
  const call = focused.mock.calls.at(-1)
  return call ? { element: focused.mock.contexts.at(-1) as HTMLElement, options: call[0] as FocusOptions | undefined } : null
}

// O passo como a página o declara: o bloco de foco da chave, levado à linha de
// foco (`block: 'start'`), com o título DENTRO dele — o título sobe junto com o
// campo, nunca fica para trás.
async function expectStepRevealed (step: 'phone' | 'code' | 'welcome', title: string) {
  const block = document.querySelector<HTMLElement>(`[data-focus-target="${step}"]`)
  expect(block).not.toBeNull()
  await vi.waitFor(() => expect(lastScroll()?.element).toBe(block))
  expect(lastScroll()?.options).toMatchObject({ block: 'start' })
  expect(block!.querySelector('h1')?.textContent?.trim()).toBe(title)
  // O campo recebe o foco sem o navegador rolar até ele.
  expect(lastFocus()?.options).toEqual({ preventScroll: true })
  expect(block!.contains(document.activeElement)).toBe(true)
  return document.activeElement as HTMLElement
}

async function openNameGate () {
  // Chegada pelo access link (`/entrar?welcome=1`): a sessão JÁ está autenticada
  // e o passo do nome abre no setup, semeado pela sessão.
  const session = useShopSession()
  session.reset()
  session.setFromAuthSession({
    is_authenticated: true,
    customer_name: '',
    requires_welcome: true,
    welcome_asks_name: true,
    welcome_asks_marketing: true,
    welcome_suggested_name: ''
  })
  const page = await mountSuspended(LoginPage, { route: '/entrar?welcome=1&next=%2Fconta', attachTo: document.body })
  mounted.push(page)
  await flushPromises()
  return page
}

function continuar (page: any) {
  return page.findAll('button[type="submit"]').find((b: any) => b.text().includes('Continuar'))!
}

describe('login — o passo do nome', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    fetchMock.mockReset()
    fetchMock.mockImplementation(routeFetch)
    navigate.mockReset()
    scrolled = vi.fn()
    Element.prototype.scrollIntoView = scrolled as unknown as Element['scrollIntoView']
    focused = vi.spyOn(HTMLElement.prototype, 'focus')
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
    Element.prototype.scrollIntoView = nativeScrollIntoView
    focused.mockRestore()
  })

  it('pede só o nome: título, campo e Continuar — sem bloco de novidades', async () => {
    const page = await openNameGate()

    expect(page.find('h1').text()).toBe('Como podemos te chamar?')
    expect(page.find('form[data-login-welcome]').exists()).toBe(true)
    expect(page.find('#welcome-name').exists()).toBe(true)
    expect(page.find('[data-login-marketing]').exists()).toBe(false)
    expect(page.find('#welcome-marketing').exists()).toBe(false)
    expect(page.text()).not.toMatch(/Antes de entrar|Uma pergunta rápida|Novidades|WhatsApp/)
    // A declaração de maioridade pertence à ENTRADA, não ao gate (já autenticado).
    expect(page.find('[data-login-adult-declaration]').exists()).toBe(false)
    // Sem nome, Continuar espera.
    expect(continuar(page).attributes('disabled')).toBeDefined()
  })

  it('Continuar grava o nome no perfil e segue — sem falar com marketing-prompt', async () => {
    const page = await openNameGate()

    await page.find('#welcome-name').setValue('  Talita  ')
    await flushPromises()
    expect(continuar(page).attributes('disabled')).toBeUndefined()
    await page.find('form[data-login-welcome]').trigger('submit')
    await flushPromises()

    const patches = callsTo('/api/v1/account/profile/').filter(([, o]) => (o as any)?.method === 'PATCH')
    expect(patches).toHaveLength(1)
    expect((patches[0]![1] as any).body).toEqual({ first_name: 'Talita' })
    expect(callsTo('/api/v1/account/marketing-prompt/')).toHaveLength(0)
    expect(navigate).toHaveBeenCalledWith('/conta')
    expect(useShopSession().customerName.value).toBe('Talita')
    expect(useShopSession().requiresWelcome.value).toBe(false)
    // A pergunta de novidades continua pendente para o sheet, na página de destino.
    expect(useShopSession().welcomeAsksMarketing.value).toBe(true)
  })

  it('"Deixar para depois" segue sem gravar nada', async () => {
    const page = await openNameGate()

    const later = page.findAll('button').find((b: any) => b.text().includes('Deixar para depois'))!
    await later.trigger('click')
    await flushPromises()

    expect(callsTo('/api/v1/account/profile/').filter(([, o]) => (o as any)?.method === 'PATCH')).toHaveLength(0)
    expect(callsTo('/api/v1/account/marketing-prompt/')).toHaveLength(0)
    expect(navigate).toHaveBeenCalledWith('/conta')
    expect(useShopSession().requiresWelcome.value).toBe(false)
  })

  it('ao chegar no passo do nome, o bloco com o título vai à linha de foco e o campo recebe o foco', async () => {
    await openNameGate()

    const active = await expectStepRevealed('welcome', 'Como podemos te chamar?')
    expect(active.id).toBe('welcome-name')
  })

  it('a troca para o passo do código leva o bloco do código à linha de foco, com o foco no 1º dígito', async () => {
    const session = useShopSession()
    session.reset()
    const page = await mountSuspended(LoginPage, { route: '/entrar', attachTo: document.body })
    mounted.push(page)
    await flushPromises()
    // Na chegada ao passo do telefone, com o bloco à vista, nada se move.
    expect(scrolled).not.toHaveBeenCalled()

    await page.findAll('button').find((b: any) => b.text().includes('Receber código por SMS'))!.trigger('click')
    await flushPromises()
    await page.find('#login-phone').setValue('43999998888')
    await page.find('form').trigger('submit')
    await flushPromises()

    expect(page.find('form[data-login-welcome]').exists()).toBe(false)
    expect(page.text()).toContain('Código de 6 dígitos')
    const active = await expectStepRevealed('code', 'Informe o código')
    expect(active.tagName).toBe('INPUT')
    expect(active.getAttribute('aria-label')).toBe('Dígito 1 de 6')
  })

  it('"Trocar telefone" volta ao bloco do telefone, com o foco no campo do número', async () => {
    const session = useShopSession()
    session.reset()
    const page = await mountSuspended(LoginPage, { route: '/entrar', attachTo: document.body })
    mounted.push(page)
    await flushPromises()

    await page.findAll('button').find((b: any) => b.text().includes('Receber código por SMS'))!.trigger('click')
    await flushPromises()
    await page.find('#login-phone').setValue('43999998888')
    await page.find('form').trigger('submit')
    await flushPromises()
    await expectStepRevealed('code', 'Informe o código')

    await page.findAll('button').find((b: any) => b.text().includes('Trocar telefone'))!.trigger('click')
    await flushPromises()

    const active = await expectStepRevealed('phone', 'Vamos entrar?')
    expect(active.id).toBe('login-phone')
  })
})
