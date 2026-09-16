import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import LoginPage from '~/pages/entrar.vue'

// O gate de boas-vindas passa a fazer a pergunta de novidades. O que só a
// PÁGINA decide, e por isso se monta a tela:
//
// - a chave nasce desligada e o campo de data só existe com ela ligada;
// - os três caminhos falam com o servidor do jeito certo: ligada = PATCH do
//   perfil (aniversário) + resposta `whatsapp: true`; desligada = só a resposta
//   `whatsapp: false`; "Deixar para depois" = a mesma resposta `false`.
//   Em nenhum deles sai um opt-out (`enabled: false` em preferences/notifications).

const { fetchMock, navigate, sonner } = vi.hoisted(() => {
  const sonner: any = vi.fn()
  sonner.success = vi.fn()
  sonner.error = vi.fn()
  sonner.info = vi.fn()
  return { fetchMock: vi.fn(), navigate: vi.fn(), sonner }
})
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('navigateTo', () => navigate)
// `useSonner` é o `toast` do vue-sonner reexportado com outro nome (nuxt.config):
// o mock tem de ir no módulo de origem, senão a página segue falando com o real.
vi.mock('vue-sonner', async (importOriginal) => ({ ...(await importOriginal<object>()), toast: sonner }))

function routeFetch (url: string, options?: { method?: string }) {
  const method = (options?.method || 'GET').toUpperCase()
  // A home é `lazy` e pode ainda não ter chegado quando o gate abre: a página
  // já trata `null`. O que este teste mede não depende dela.
  if (url.endsWith('/api/v1/storefront/home/')) return Promise.resolve(null)
  if (url.endsWith('/api/v1/account/profile/') && method === 'GET') return Promise.resolve({ first_name: 'Ana', birthday: '' })
  if (url.endsWith('/api/v1/account/marketing-prompt/')) return Promise.resolve({ ok: true, whatsapp_opted_in: true })
  return Promise.resolve({})
}

function callsTo (suffix: string) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(suffix))
}

const mounted: Array<{ unmount: () => void }> = []

async function openGate (asks: { name: boolean, marketing: boolean }) {
  // Chegada pelo access link (`/entrar?welcome=1`): a sessão JÁ está autenticada e
  // o gate abre no setup, semeado pela sessão.
  const session = useShopSession()
  session.reset()
  session.setFromAuthSession({
    is_authenticated: true,
    customer_name: asks.name ? '' : 'Ana Silva',
    requires_welcome: true,
    welcome_asks_name: asks.name,
    welcome_asks_marketing: asks.marketing,
    welcome_suggested_name: asks.name ? '' : 'Ana Silva'
  })
  const page = await mountSuspended(LoginPage, { route: '/entrar?welcome=1&next=%2Fconta' })
  mounted.push(page)
  await flushPromises()
  return page
}

async function continuar (page: any) {
  const submit = page.findAll('button[type="submit"]').find((b: any) => b.text().includes('Continuar'))!
  expect(submit.exists()).toBe(true)
  expect(submit.attributes('disabled')).toBeUndefined()
  await page.find('form[data-login-welcome]').trigger('submit')
  await flushPromises()
}

describe('login — a pergunta de novidades no gate de boas-vindas', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    fetchMock.mockReset()
    fetchMock.mockImplementation(routeFetch)
    navigate.mockReset()
    sonner.info.mockReset()
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
  })

  it('opens on the marketing question alone, with the switch off and no birthday field', async () => {
    const page = await openGate({ name: false, marketing: true })

    expect(page.find('form[data-login-welcome]').exists()).toBe(true)
    expect(page.find('[data-login-marketing]').exists()).toBe(true)
    expect(page.text()).toContain('Novidades da Nelson')
    expect(page.text()).toContain('Você muda isso quando quiser em Conta › Preferências.')
    // Só a pergunta de novidades: nenhum campo de nome.
    expect(page.find('#welcome-name').exists()).toBe(false)
    const toggle = page.find('#welcome-marketing')
    expect(toggle.exists()).toBe(true)
    expect(toggle.attributes('aria-checked')).toBe('false')
    expect(page.find('#welcome-birthday').exists()).toBe(false)
  })

  it('asks the name too when the name is missing', async () => {
    const page = await openGate({ name: true, marketing: true })
    expect(page.find('#welcome-name').exists()).toBe(true)
    expect(page.find('#welcome-marketing').exists()).toBe(true)
  })

  it('reveals the birthday only after the switch is turned on, and requires it', async () => {
    const page = await openGate({ name: false, marketing: true })

    await page.find('#welcome-marketing').trigger('click')
    await flushPromises()

    expect(page.find('#welcome-marketing').attributes('aria-checked')).toBe('true')
    const birthday = page.find('#welcome-birthday')
    expect(birthday.exists()).toBe(true)
    expect(birthday.attributes('type')).toBe('date')
    expect(page.text()).toContain('Novidades só vão para maiores de 18. A data fica no seu perfil.')
    // Sem a data, o botão não segue.
    const submit = page.findAll('button[type="submit"]').find((b: any) => b.text().includes('Continuar'))!
    expect(submit.attributes('disabled')).toBeDefined()
  })

  it('switch on: saves the birthday to the profile, then answers whatsapp=true — and never an opt-out', async () => {
    const page = await openGate({ name: false, marketing: true })

    await page.find('#welcome-marketing').trigger('click')
    await flushPromises()
    await page.find('#welcome-birthday').setValue('1990-05-15')
    await flushPromises()
    await continuar(page)

    const patches = callsTo('/api/v1/account/profile/').filter(([, o]) => (o as any)?.method === 'PATCH')
    expect(patches).toHaveLength(1)
    // O nome não foi pedido: o PATCH leva o first_name que JÁ está no perfil, não o nome completo.
    expect((patches[0]![1] as any).body).toEqual({ birthday: '1990-05-15', first_name: 'Ana' })

    const answers = callsTo('/api/v1/account/marketing-prompt/')
    expect(answers).toHaveLength(1)
    expect((answers[0]![1] as any)).toMatchObject({ method: 'POST', body: { whatsapp: true } })
    expect(callsTo('/api/v1/account/preferences/notifications/')).toHaveLength(0)
    expect(navigate).toHaveBeenCalledWith('/conta')
  })

  it('switch off: answers whatsapp=false only — no profile write, no opt-out', async () => {
    const page = await openGate({ name: false, marketing: true })

    await continuar(page)

    expect(callsTo('/api/v1/account/profile/').filter(([, o]) => (o as any)?.method === 'PATCH')).toHaveLength(0)
    const answers = callsTo('/api/v1/account/marketing-prompt/')
    expect(answers).toHaveLength(1)
    expect((answers[0]![1] as any).body).toEqual({ whatsapp: false })
    expect(callsTo('/api/v1/account/preferences/notifications/')).toHaveLength(0)
    expect(navigate).toHaveBeenCalledWith('/conta')
  })

  it('"Deixar para depois" stamps the question as asked and moves on — never an opt-out', async () => {
    const page = await openGate({ name: false, marketing: true })

    const later = page.findAll('button').find((b: any) => b.text().includes('Deixar para depois'))!
    await later.trigger('click')
    await flushPromises()

    const answers = callsTo('/api/v1/account/marketing-prompt/')
    expect(answers).toHaveLength(1)
    expect((answers[0]![1] as any).body).toEqual({ whatsapp: false })
    expect(callsTo('/api/v1/account/preferences/notifications/')).toHaveLength(0)
    expect(navigate).toHaveBeenCalledWith('/conta')
    expect(useShopSession().requiresWelcome.value).toBe(false)
  })

  it('name + switch on: one PATCH with both, then the answer', async () => {
    const page = await openGate({ name: true, marketing: true })

    await page.find('#welcome-name').setValue('Talita')
    await page.find('#welcome-marketing').trigger('click')
    await flushPromises()
    await page.find('#welcome-birthday').setValue('1990-05-15')
    await flushPromises()
    await continuar(page)

    const patches = callsTo('/api/v1/account/profile/').filter(([, o]) => (o as any)?.method === 'PATCH')
    expect(patches).toHaveLength(1)
    expect((patches[0]![1] as any).body).toEqual({ first_name: 'Talita', birthday: '1990-05-15' })
    expect(callsTo('/api/v1/account/marketing-prompt/')).toHaveLength(1)
    expect(navigate).toHaveBeenCalledWith('/conta')
  })

  it('tells the person when the server could not opt them in (under 18 by the date)', async () => {
    fetchMock.mockImplementation((url: string, options?: { method?: string }) => {
      if (String(url).endsWith('/api/v1/account/marketing-prompt/')) return Promise.resolve({ ok: true, whatsapp_opted_in: false })
      return routeFetch(String(url), options)
    })
    const page = await openGate({ name: false, marketing: true })

    await page.find('#welcome-marketing').trigger('click')
    await flushPromises()
    await page.find('#welcome-birthday').setValue('2015-01-01')
    await flushPromises()
    await continuar(page)

    expect(callsTo('/api/v1/account/marketing-prompt/')).toHaveLength(1)
    expect(navigate).toHaveBeenCalledWith('/conta')
    expect(sonner.info).toHaveBeenCalledWith('Novidades só vão para maiores de 18. Sua resposta ficou guardada.')
  })
})
