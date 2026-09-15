// StockNotifyButton: telefone vem da identidade canônica. Anônimo preserva
// página + produto no login e confirma o opt-in depois, sem redigitar o número.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import StockNotifyButton from '~/components/StockNotifyButton.vue'

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  navigate: vi.fn(),
  replace: vi.fn(),
  resolve: vi.fn(),
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  route: {
    path: '/menu',
    fullPath: '/menu',
    query: {} as Record<string, string>,
    hash: ''
  }
}))

mockNuxtImport('$fetch', () => mocks.fetch)
mockNuxtImport('navigateTo', () => mocks.navigate)
mockNuxtImport('useRoute', () => () => mocks.route)
mockNuxtImport('useRouter', () => () => ({
  replace: mocks.replace,
  resolve: mocks.resolve,
  afterEach: vi.fn(),
  beforeResolve: vi.fn()
}))
mockNuxtImport('useSonner', () => {
  return mocks.toast
})

async function setAuthenticated (value: boolean) {
  const { useShopSession } = await import('~/composables/useShopSession')
  const session = useShopSession()
  session.reset()
  if (value) session.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana', customer_phone: '43999' })
}

describe('StockNotifyButton', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
    mocks.fetch.mockReset()
    mocks.navigate.mockReset()
    mocks.replace.mockReset().mockResolvedValue(undefined)
    mocks.resolve.mockReset().mockImplementation(({ path, query, hash }) => {
      const params = new URLSearchParams(query).toString()
      return { fullPath: `${path}${params ? `?${params}` : ''}${hash || ''}` }
    })
    Object.assign(mocks.route, { path: '/menu', fullPath: '/menu', query: {}, hash: '' })
    mocks.toast.mockClear()
    mocks.toast.success.mockClear()
    mocks.toast.error.mockClear()
    vi.stubGlobal('$fetch', mocks.fetch)
    document.body.innerHTML = ''
  })

  it('shows the calm confirmed state when already subscribed', async () => {
    await setAuthenticated(true)
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', subscribed: true }
    })

    expect(wrapper.text()).toContain('Aviso ativo')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Gerenciar este aviso')
    expect(wrapper.get('a').attributes('href')).toBe('/conta/preferencias#avisos-produtos')
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('legacy anonymous reload can still recover its exact management capability', async () => {
    await setAuthenticated(false)
    mocks.fetch.mockResolvedValue({ active: true, management_url: '/gerenciar-aviso#recovered-capability' })
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', subscribed: true }
    })

    await new Promise(resolve => setTimeout(resolve, 0))
    await nextTick()

    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(mocks.fetch.mock.calls[0]?.[0]).toContain('/availability/PAO/notify/')
    expect(mocks.fetch.mock.calls[0]?.[1]).toMatchObject({ method: 'GET', credentials: 'include' })
    expect(wrapper.get('a').attributes('href')).toBe('/gerenciar-aviso#recovered-capability')
  })

  it('anonymous click preserves page and product in the canonical login return', async () => {
    await setAuthenticated(false)
    Object.assign(mocks.route, {
      path: '/menu',
      fullPath: '/menu?categoria=paes#fornada',
      query: { categoria: 'paes' },
      hash: '#fornada'
    })
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', subscribed: false }
    })

    expect(wrapper.text()).toContain('Entrar para ser avisado')
    expect(wrapper.get('button').attributes('aria-label')).toContain('Entrar para ativar avisos recorrentes')
    await wrapper.get('button').trigger('click')

    expect(mocks.fetch).not.toHaveBeenCalled()
    expect(mocks.navigate).toHaveBeenCalledWith(
      `/entrar?next=${encodeURIComponent('/menu?categoria=paes&aviso=PAO#fornada')}`
    )
  })

  it('authenticated return offers explicit confirmation and clears only its intention after success', async () => {
    await setAuthenticated(true)
    Object.assign(mocks.route, {
      path: '/menu',
      fullPath: '/menu?categoria=paes&aviso=PAO#fornada',
      query: { categoria: 'paes', aviso: 'PAO' },
      hash: '#fornada'
    })
    mocks.fetch.mockResolvedValue({ management_url: '/gerenciar-aviso#opaque-capability' })
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', subscribed: false }
    })

    expect(wrapper.text()).toContain('WhatsApp confirmado. Confirme para ativar este aviso.')
    expect(wrapper.get('button').text()).toContain('Confirmar aviso')
    expect(wrapper.get('button').attributes('autofocus')).toBeDefined()
    const replaceCallsBeforeClick = mocks.replace.mock.calls.length
    await wrapper.get('button').trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    await nextTick()

    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(mocks.fetch.mock.calls[0]?.[0]).toContain('/availability/PAO/notify/')
    expect(mocks.fetch.mock.calls[0]?.[1]).toMatchObject({ method: 'POST', body: {} })
    expect(mocks.replace.mock.calls.length).toBe(replaceCallsBeforeClick + 1)
    expect(mocks.replace).toHaveBeenLastCalledWith({
      path: '/menu',
      query: { categoria: 'paes' },
      hash: '#fornada'
    })
    expect(wrapper.text()).toContain('Aviso ativo')
    expect(wrapper.get('a').attributes('href')).toBe('/gerenciar-aviso#opaque-capability')
  })

  it('keeps the preserved intention when subscribe fails so retry is the next action', async () => {
    await setAuthenticated(true)
    Object.assign(mocks.route, { query: { aviso: 'PAO' } })
    mocks.fetch.mockRejectedValue(new Error('offline'))
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', subscribed: false }
    })

    const replaceCallsBeforeClick = mocks.replace.mock.calls.length
    await wrapper.get('button').trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(mocks.replace.mock.calls.length).toBe(replaceCallsBeforeClick)
    expect(wrapper.text()).toContain('Confirmar aviso')
  })

  it('authenticated ordinary one-click subscribe uses the account identity', async () => {
    await setAuthenticated(true)
    mocks.fetch.mockResolvedValue({ management_url: '/gerenciar-aviso#opaque-capability' })
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', subscribed: false }
    })

    const replaceCallsBeforeClick = mocks.replace.mock.calls.length
    await wrapper.get('button').trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    await nextTick()

    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(mocks.fetch.mock.calls[0]?.[1]?.body).toEqual({})
    expect(mocks.replace.mock.calls.length).toBe(replaceCallsBeforeClick)
    expect(wrapper.text()).toContain('Aviso ativo')
  })

  it('renders an accessible label when not subscribed', async () => {
    await setAuthenticated(true)
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', pill: true, subscribed: false }
    })
    expect(wrapper.get('button').attributes('aria-label')).toBe('Ativar avisos recorrentes quando Pão voltar')
  })
})
