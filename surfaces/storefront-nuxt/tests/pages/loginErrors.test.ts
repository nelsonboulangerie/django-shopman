import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import LoginPage from '~/pages/entrar.vue'

// Beta 05/11. LOJA-04: "4399" ia ao servidor e o aviso subia para o topo da página,
// longe do campo, e continuava lá depois da correção. LOJA-03: o conflito de
// identidade vinha sob o título "Código não confere", com o código CERTO.

const { fetchMock, navigate } = vi.hoisted(() => ({ fetchMock: vi.fn(), navigate: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('navigateTo', () => navigate)

const conflict = Object.assign(new Error('400'), {
  status: 400,
  statusCode: 400,
  data: {
    detail: 'Este número aparece em mais de um cadastro e, por segurança, não entramos por ele agora. Fale com a gente para resolver.',
    field: null,
    errors: {},
    error_code: 'identity_conflict'
  }
})

function routeFetch (url: string) {
  const path = String(url)
  if (path.endsWith('/api/auth/device-check/')) return Promise.resolve({ ok: true, trusted: false, phone: '+5543999998888' })
  if (path.endsWith('/api/auth/request-code/')) {
    return Promise.resolve({ ok: true, phone: '+5543999998888', delivery_method: 'sms', delivery_label: 'SMS', dev_console_hint: false })
  }
  if (path.endsWith('/api/auth/verify-code/')) return Promise.reject(conflict)
  return Promise.resolve(null)
}

const mounted: Array<{ unmount: () => void }> = []
const nativeCredentials = Object.getOwnPropertyDescriptor(navigator, 'credentials')

async function openSmsForm () {
  useShopSession().reset()
  const page = await mountSuspended(LoginPage, { route: '/entrar', attachTo: document.body })
  mounted.push(page)
  await flushPromises()
  await page.findAll('button').find((b: any) => b.text().includes('Prefere receber um código por SMS?'))!.trigger('click')
  await flushPromises()
  return page
}

function calls (suffix: string) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(suffix))
}

describe('login: erros com o título certo e no lugar certo', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    fetchMock.mockReset()
    fetchMock.mockImplementation(routeFetch)
    navigate.mockReset()
    Element.prototype.scrollIntoView = vi.fn() as unknown as Element['scrollIntoView']
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
    delete (window as unknown as { OTPCredential?: unknown }).OTPCredential
    if (nativeCredentials) Object.defineProperty(navigator, 'credentials', nativeCredentials)
    else delete (navigator as unknown as { credentials?: unknown }).credentials
  })

  it('LOJA-04: número incompleto não vai ao servidor, o erro fica sob o campo e sai ao corrigir', async () => {
    const page = await openSmsForm()
    await page.find('#login-phone').setValue('4399')
    await page.find('form').trigger('submit')
    await flushPromises()

    expect(calls('/api/auth/request-code/')).toHaveLength(0)
    expect(page.find('#login-error').exists()).toBe(false)
    const inline = page.find('[data-login-phone-error]')
    expect(inline.exists()).toBe(true)
    expect(inline.text()).toContain('Informe o DDD e o número')
    expect(page.find('#login-phone').attributes('aria-invalid')).toBe('true')

    await page.find('#login-phone').setValue('43991374682')
    await flushPromises()
    expect(page.find('[data-login-phone-error]').exists()).toBe(false)
  }, 30_000)

  it('LOJA-03: conflito de identidade tem título próprio e o botão de falar com a loja no aviso', async () => {
    // O código CERTO chega pelo WebOTP e a confirmação sai sozinha.
    ;(window as unknown as { OTPCredential?: unknown }).OTPCredential = function () {}
    Object.defineProperty(navigator, 'credentials', {
      value: { get: vi.fn(() => Promise.resolve({ type: 'otp', code: '123456' })) },
      configurable: true
    })
    useNuxtData('shopman-shell').data.value = { shell: { public_config: { whatsapp_url: 'https://wa.me/554333231997' } } }
    const page = await openSmsForm()
    await page.find('#login-phone').setValue('43999998888')
    await page.find('form').trigger('submit')
    await flushPromises()

    await vi.waitFor(() => expect(calls('/api/auth/verify-code/')).toHaveLength(1))
    await flushPromises()

    const alert = page.find('#login-error')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('Não conseguimos entrar com este número')
    expect(alert.text()).not.toContain('Código não confere')
    expect(alert.find('[data-login-error-support]').exists()).toBe(true)
    // Um "Falar com a loja" só: o cartão de ajuda do rodapé sai enquanto o aviso o oferece.
    expect(page.findAll('a').filter((a: any) => a.text().includes('Falar com a loja'))).toHaveLength(1)
    expect(page.find('[data-login-support]').exists()).toBe(false)
    useNuxtData('shopman-shell').data.value = null
  }, 30_000)

  it('LOJA-13: vindo do coração, a entrada diz por que pediu o login', async () => {
    useShopSession().reset()
    const page = await mountSuspended(LoginPage, { route: '/entrar?motivo=favorito&next=/produto/TRADI', attachTo: document.body })
    mounted.push(page)
    await flushPromises()

    expect(page.text()).toContain('Entre para guardar seus favoritos.')
  }, 30_000)
})
