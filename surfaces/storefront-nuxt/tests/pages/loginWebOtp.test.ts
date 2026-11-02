import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import LoginPage from '~/pages/entrar.vue'

// O código do SMS preenchido sozinho no Chrome do Android (WebOTP). O SMS termina com
// `@www.nelsonboulangerie.com.br #<código>`; a página pede o código ao navegador só
// enquanto a etapa do código está na tela, e aborta ao sair dela.

const { fetchMock, navigate } = vi.hoisted(() => ({ fetchMock: vi.fn(), navigate: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('navigateTo', () => navigate)

function routeFetch (url: string) {
  const path = String(url)
  if (path.endsWith('/api/auth/device-check/')) return Promise.resolve({ ok: true, trusted: false, phone: '+5543999998888' })
  if (path.endsWith('/api/auth/request-code/')) {
    return Promise.resolve({ ok: true, phone: '+5543999998888', delivery_method: 'sms', delivery_label: 'SMS', dev_console_hint: false })
  }
  if (path.endsWith('/api/auth/verify-code/')) {
    return Promise.resolve({ ok: true, phone: '+5543999998888', is_authenticated: true, customer_name: 'Talita', requires_welcome: false })
  }
  return Promise.resolve(null)
}

const mounted: Array<{ unmount: () => void }> = []
let credentialsGet: ReturnType<typeof vi.fn>
const nativeCredentials = Object.getOwnPropertyDescriptor(navigator, 'credentials')

function installWebOtp (impl: (options: { signal: AbortSignal }) => Promise<unknown>) {
  ;(window as unknown as { OTPCredential?: unknown }).OTPCredential = function () {}
  credentialsGet = vi.fn(impl)
  Object.defineProperty(navigator, 'credentials', { value: { get: credentialsGet }, configurable: true })
}

async function openCodeStep () {
  useShopSession().reset()
  const page = await mountSuspended(LoginPage, { route: '/entrar', attachTo: document.body })
  mounted.push(page)
  await flushPromises()
  await page.findAll('button').find((b: any) => b.text().includes('Prefere receber um código por SMS?'))!.trigger('click')
  await flushPromises()
  await page.find('#login-phone').setValue('43999998888')
  await page.find('form').trigger('submit')
  await flushPromises()
  return page
}

function verifyCalls () {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/api/auth/verify-code/'))
}

describe('login — código do SMS pelo WebOTP', () => {
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

  it('o código que o Chrome entrega preenche o campo e confirma sozinho', async () => {
    installWebOtp(() => Promise.resolve({ type: 'otp', code: '123456' }))
    await openCodeStep()
    await flushPromises()

    expect(credentialsGet).toHaveBeenCalledTimes(1)
    const options = credentialsGet.mock.calls[0]![0]
    expect(options.otp).toEqual({ transport: ['sms'] })
    expect(options.signal).toBeInstanceOf(AbortSignal)
    await vi.waitFor(() => expect(verifyCalls()).toHaveLength(1))
    expect((verifyCalls()[0]![1] as any).body).toEqual({ phone: '+5543999998888', code: '123456' })
  })

  it('só pede na etapa do código, e sair dela aborta a espera', async () => {
    let signal: AbortSignal | undefined
    installWebOtp(options => {
      signal = options.signal
      return new Promise(() => {})
    })
    useShopSession().reset()
    const page = await mountSuspended(LoginPage, { route: '/entrar', attachTo: document.body })
    mounted.push(page)
    await flushPromises()
    expect(credentialsGet).not.toHaveBeenCalled()
    page.unmount()
    mounted.pop()

    const codePage = await openCodeStep()
    expect(codePage.text()).toContain('Código de 6 dígitos')
    expect(credentialsGet).toHaveBeenCalledTimes(1)
    expect(signal?.aborted).toBe(false)

    await codePage.findAll('button').find((b: any) => b.text().includes('Trocar telefone'))!.trigger('click')
    await flushPromises()
    expect(signal?.aborted).toBe(true)
    expect(verifyCalls()).toHaveLength(0)
  })

  it('navegador sem WebOTP não chama nada, e o campo segue digitável', async () => {
    credentialsGet = vi.fn()
    Object.defineProperty(navigator, 'credentials', { value: { get: credentialsGet }, configurable: true })
    const page = await openCodeStep()

    expect(page.text()).toContain('Código de 6 dígitos')
    expect(credentialsGet).not.toHaveBeenCalled()
    expect(page.find('input[autocomplete="one-time-code"]').exists()).toBe(true)
  })
})
