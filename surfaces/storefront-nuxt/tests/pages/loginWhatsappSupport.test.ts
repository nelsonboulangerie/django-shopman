import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import LoginPage from '~/pages/entrar.vue'

// #3271: com a mensagem já recebida (falta o toque em "Liberar o Chrome"), o cartão de
// ajuda perguntava "Enviou e nada aconteceu?", logo abaixo de "Sua mensagem chegou". Só
// nesse estado a pergunta passa a ser a da resposta que pode não ter chegado; a saída
// ("Falar com a loja") fica igual. Nos outros estados, nada muda.

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)

let claimStatus = 'pending'

function routeFetch (url: string) {
  const path = String(url)
  if (path.endsWith('/api/v1/auth/whatsapp/claim/')) return Promise.resolve({ status: claimStatus })
  return Promise.resolve(null)
}

const mounted: Array<{ unmount: () => void }> = []

/** A aba volta do WhatsApp: a espera e a mensagem gerada estão guardadas na sessão. */
async function openWaiting () {
  const now = Date.now()
  sessionStorage.setItem('shopman:wa-return', JSON.stringify({ version: 1, startedAt: now, expiresAt: now + 60_000 }))
  sessionStorage.setItem('shopman:wa-verify-start', JSON.stringify({
    code: 'NB-HAKZKG',
    message: 'Olá! Quero entrar no site da Nelson Boulangerie (ref. NB-HAKZKG)',
    deep_link: 'https://wa.me/554333231997?text=x',
    wa_number: '554333231997',
    return_mode: 'release_this_tab',
    return_button: 'Liberar o Chrome',
    saved_at: now
  }))
  useShopSession().reset()
  const page = await mountSuspended(LoginPage, { route: '/entrar?next=/finalizar', attachTo: document.body })
  mounted.push(page)
  await flushPromises()
  await vi.waitFor(() => expect(page.find('[data-login-whatsapp-waiting]').exists()).toBe(true))
  return page
}

describe('login: a pergunta da ajuda acompanha o que já aconteceu', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    sessionStorage.clear()
    fetchMock.mockReset()
    fetchMock.mockImplementation(routeFetch)
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true })
    useNuxtData('shopman-shell').data.value = { shell: { public_config: { whatsapp_url: 'https://wa.me/554333231997' } } }
    Element.prototype.scrollIntoView = vi.fn() as unknown as Element['scrollIntoView']
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
    useNuxtData('shopman-shell').data.value = null
    sessionStorage.clear()
  })

  it('a mensagem chegou e falta liberar: a ajuda pergunta pela resposta, não pelo envio', async () => {
    claimStatus = 'awaiting_release'
    const page = await openWaiting()

    await vi.waitFor(() => expect(page.find('[data-login-whatsapp-arrived]').exists()).toBe(true))
    const support = page.find('[data-login-support]')
    expect(support.text()).toContain('Não recebeu a resposta no WhatsApp?')
    expect(support.text()).not.toContain('Enviou e nada aconteceu?')
    expect(support.text()).toContain('Fale com a loja e resolvemos juntos.')
    expect(support.text()).toContain('Falar com a loja')
  }, 30_000)

  it('esperando a mensagem, a ajuda segue "Enviou e nada aconteceu?"', async () => {
    claimStatus = 'pending'
    const page = await openWaiting()

    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/api/v1/auth/whatsapp/claim/'))).toBe(true))
    await flushPromises()
    expect(page.find('[data-login-whatsapp-arrived]').exists()).toBe(false)
    const support = page.find('[data-login-support]')
    expect(support.text()).toContain('Enviou e nada aconteceu?')
    expect(support.text()).not.toContain('Não recebeu a resposta no WhatsApp?')
    expect(support.text()).toContain('Falar com a loja')
  }, 30_000)
})
