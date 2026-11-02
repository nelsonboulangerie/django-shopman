import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import LoginPage from '~/pages/entrar.vue'

// Entrar pela chave deste aparelho (escada sem fricção, decisão do dono de 23/10).
//
// O que só a PÁGINA decide, e por isso se monta a tela:
// - a porta só aparece onde a chave mora (navegador que ativou ou já entrou com ela);
//   para os outros, a tela de sempre, sem um botão que levaria a um diálogo vazio;
// - a chave aberta segue o mesmo fim das outras portas: nome, se faltar, com o passo
//   levado à linha de foco (`useNextFocus`); senão, a festa e o destino;
// - cancelar o diálogo do aparelho não é erro: nada vermelho, WhatsApp abaixo.

const { fetchMock, navigate, passkey } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  navigate: vi.fn(),
  passkey: {
    supported: true,
    remembered: true,
    signIn: vi.fn()
  }
}))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('navigateTo', () => navigate)
mockNuxtImport('usePasskey', () => () => {
  const busy = ref(false)
  const error = ref('')
  return {
    busy,
    error,
    signIn: async () => {
      const result = await passkey.signIn()
      if (result === 'failed') {
        error.value = 'Não reconhecemos esta chave. Entre pelo WhatsApp.'
        return null
      }
      if (result) useShopSession().setFromAuthSession(result)
      return result
    },
    passkeySupported: () => passkey.supported,
    passkeyRememberedHere: () => passkey.remembered
  }
})

function routeFetch (url: string) {
  if (String(url).endsWith('/api/v1/auth/whatsapp/start/')) {
    return Promise.resolve({
      code: 'NB-AbCd',
      message: '#menu NB-AbCd',
      deep_link: 'https://wa.me/554333231997?text=x',
      wa_number: '554333231997',
      return_mode: 'message_button',
      return_button: 'Voltar à loja'
    })
  }
  return Promise.resolve(null)
}

const mounted: Array<{ unmount: () => void }> = []
let scrolled: ReturnType<typeof vi.fn>
const nativeScrollIntoView = Element.prototype.scrollIntoView

async function openLogin () {
  useShopSession().reset()
  const page = await mountSuspended(LoginPage, { route: '/entrar?next=%2Fconta', attachTo: document.body })
  mounted.push(page)
  await flushPromises()
  return page
}

function session (overrides: Record<string, unknown> = {}) {
  return {
    is_authenticated: true,
    customer_ref: 'CUST-1',
    customer_name: 'Talita Souza',
    customer_phone: '+5543999998888',
    customer_email: '',
    requires_welcome: false,
    welcome_asks_name: false,
    welcome_asks_marketing: false,
    welcome_suggested_name: '',
    ...overrides
  }
}

describe('login — entrar com a chave deste aparelho', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    fetchMock.mockReset()
    fetchMock.mockImplementation(routeFetch)
    navigate.mockReset()
    passkey.supported = true
    passkey.remembered = true
    passkey.signIn.mockReset()
    scrolled = vi.fn()
    Element.prototype.scrollIntoView = scrolled as unknown as Element['scrollIntoView']
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
    Element.prototype.scrollIntoView = nativeScrollIntoView
    vi.useRealTimers()
  })

  it('onde a chave mora, a porta aparece antes do WhatsApp', async () => {
    const page = await openLogin()

    const button = page.find('[data-login-passkey]')
    expect(button.exists()).toBe(true)
    expect(button.text()).toBe('Entrar com a chave deste aparelho')
    const html = page.html()
    expect(html.indexOf('data-login-passkey')).toBeLessThan(html.indexOf('data-login-whatsapp-open'))
  })

  it('onde a chave não mora, nenhum botão que levaria a um diálogo vazio', async () => {
    passkey.remembered = false
    const page = await openLogin()

    expect(page.find('[data-login-passkey]').exists()).toBe(false)
  })

  it('navegador sem passkey não oferece, mesmo lembrando', async () => {
    passkey.supported = false
    const page = await openLogin()

    expect(page.find('[data-login-passkey]').exists()).toBe(false)
  })

  it('a chave abre a sessão e segue ao destino com a festa do aparelho reconhecido', async () => {
    passkey.signIn.mockResolvedValue(session())
    const page = await openLogin()

    vi.useFakeTimers()
    await page.find('[data-login-passkey]').trigger('click')
    await flushPromises()
    expect(page.find('[data-login-moment]').text()).toContain('Bem-vindo de volta, Talita!')
    expect(page.find('[data-login-moment]').text()).toContain('Aparelho reconhecido')
    await vi.advanceTimersByTimeAsync(1500)
    expect(navigate).toHaveBeenCalledWith('/conta')
  })

  it('sem nome, a chave leva ao passo do nome, com o campo no foco', async () => {
    passkey.signIn.mockResolvedValue(session({ customer_name: '', requires_welcome: true, welcome_asks_name: true }))
    const page = await openLogin()

    await page.find('[data-login-passkey]').trigger('click')
    await flushPromises()

    const block = document.querySelector<HTMLElement>('[data-focus-target="welcome"]')
    expect(block).not.toBeNull()
    await vi.waitFor(() => expect(scrolled.mock.contexts.at(-1)).toBe(block))
    expect(document.activeElement?.id).toBe('welcome-name')
    expect(navigate).not.toHaveBeenCalled()
  })

  it('cancelar o diálogo do aparelho não pinta nada de vermelho', async () => {
    passkey.signIn.mockResolvedValue(null)
    const page = await openLogin()

    await page.find('[data-login-passkey]').trigger('click')
    await flushPromises()

    expect(page.find('#login-error').exists()).toBe(false)
    expect(page.find('[data-login-passkey]').exists()).toBe(true)
    expect(navigate).not.toHaveBeenCalled()
  })

  it('chave recusada pelo servidor diz o porquê e deixa o WhatsApp à mão', async () => {
    passkey.signIn.mockResolvedValue('failed')
    const page = await openLogin()

    await page.find('[data-login-passkey]').trigger('click')
    await flushPromises()

    expect(page.find('#login-error').text()).toContain('Não reconhecemos esta chave')
    expect(page.find('[data-login-whatsapp-open]').exists()).toBe(true)
  })
})

describe('login — o botão da resposta do WhatsApp tem o mesmo nome na tela', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    navigate.mockReset()
    passkey.remembered = false
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
  })

  it('no celular, o terceiro passo manda tocar em "Voltar à loja"', async () => {
    fetchMock.mockImplementation(routeFetch)
    const page = await openLogin()

    expect(page.find('[data-login-whatsapp-steps]').text()).toContain('Na resposta, toque em “Voltar à loja”')
  })

  it('no computador, o passo nomeia o navegador que o botão libera', async () => {
    fetchMock.mockImplementation((url: string) => String(url).endsWith('/api/v1/auth/whatsapp/start/')
      ? Promise.resolve({
        code: 'NB-AbCd',
        message: '#menu NB-AbCd',
        deep_link: 'https://wa.me/554333231997?text=x',
        wa_number: '554333231997',
        return_mode: 'release_this_tab',
        return_button: 'Liberar o Chrome'
      })
      : Promise.resolve(null))
    const page = await openLogin()

    expect(page.find('[data-login-whatsapp-steps]').text()).toContain('Na resposta, toque em “Liberar o Chrome”')
  })
})
