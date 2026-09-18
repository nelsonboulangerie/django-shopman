import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { DOMWrapper } from '@vue/test-utils'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import StockNotifyButton from '~/components/StockNotifyButton.vue'

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  navigate: vi.fn(),
  replace: vi.fn(),
  resolve: vi.fn(),
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  route: { path: '/menu', fullPath: '/menu', query: {} as Record<string, string>, hash: '' }
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
mockNuxtImport('useSonner', () => mocks.toast)

async function setAuthenticated (value: boolean) {
  const { useShopSession } = await import('~/composables/useShopSession')
  const session = useShopSession()
  session.reset()
  const transientStates = useState<Record<string, 'paused' | 'cancelled'>>('stock-notify-transient-states', () => ({}))
  transientStates.value = {}
  if (value) session.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana', customer_phone: '43999' })
}

const mountedWrappers: Array<{ unmount: () => void }> = []

async function mountStockNotify (props: { sku: string, name?: string, subscribed?: boolean, pill?: boolean }) {
  const wrapper = await mountSuspended(StockNotifyButton, { props })
  mountedWrappers.push(wrapper)
  return wrapper
}

async function flush () {
  await new Promise(resolve => setTimeout(resolve, 0))
  await nextTick()
}

async function acceptDisclosure () {
  const declaration = document.body.querySelector<HTMLElement>('[aria-label="Confirmar maioridade"]')
  const form = document.body.querySelector<HTMLFormElement>('form')
  expect(declaration).not.toBeNull()
  expect(form).not.toBeNull()
  await new DOMWrapper(declaration!).trigger('click')
  await new DOMWrapper(form!).trigger('submit')
  await flush()
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
  })

  afterEach(() => {
    for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount()
  })

  it('uses one clickable Anotado control for state and management', async () => {
    await setAuthenticated(true)
    mocks.fetch.mockResolvedValue({ active: true, management_url: '/gerenciar-aviso#capability' })
    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão', subscribed: true, pill: true })
    await flush()

    expect(wrapper.text()).toBe('Anotado')
    expect(wrapper.findAll('a')).toHaveLength(1)
    expect(wrapper.get('a').attributes('href')).toBe('/gerenciar-aviso#capability')
    expect(wrapper.get('a').attributes('aria-label')).toBe('Anotado para Pão. Gerenciar aviso')
    expect(wrapper.text()).not.toContain('Gerenciar este aviso')
    expect(mocks.fetch).toHaveBeenCalledWith(expect.stringContaining('/availability/PAO/notify/'), expect.objectContaining({ method: 'GET' }))
  })

  it('uses account preferences only when authenticated capability recovery fails', async () => {
    await setAuthenticated(true)
    mocks.fetch.mockRejectedValue(new Error('offline'))
    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão', subscribed: true, pill: true })
    await flush()

    expect(wrapper.get('a').attributes('href')).toBe('/conta/preferencias#avisos-produtos')
  })

  it('recovers a legacy anonymous management capability into the same Anotado control', async () => {
    await setAuthenticated(false)
    mocks.fetch.mockResolvedValue({ active: true, management_url: '/gerenciar-aviso#capability' })
    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão', subscribed: true })
    await flush()

    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(wrapper.get('a').attributes('href')).toBe('/gerenciar-aviso#capability')
    expect(wrapper.text()).toBe('Anotado')
  })

  it.each([
    { state: 'paused' as const, label: 'Pausado' },
    { state: 'cancelled' as const, label: 'Cancelado' }
  ])('shows the immediate $label confirmation in the same bounded control', async ({ state, label }) => {
    await setAuthenticated(true)
    const transientStates = useState<Record<string, 'paused' | 'cancelled'>>('stock-notify-transient-states', () => ({}))
    transientStates.value = { PAO: state }

    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão', subscribed: true, pill: true })

    expect(wrapper.text()).toBe(label)
    expect(wrapper.findAll('button')).toHaveLength(1)
    expect(wrapper.find('a').exists()).toBe(false)
    expect(wrapper.get('button').attributes('title')).toContain('Na próxima atualização, Me avise ficará disponível.')
    expect(wrapper.get('button').find('svg').exists()).toBe(true)
  })

  it('returns a transient paused/cancelled SKU to Me avise when the next projection is inactive', async () => {
    await setAuthenticated(true)
    const transientStates = useState<Record<string, 'paused' | 'cancelled'>>('stock-notify-transient-states', () => ({}))
    transientStates.value = { PAO: 'paused' }

    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão', subscribed: false, pill: true })

    expect(wrapper.text()).toBe('Me avise')
    expect(wrapper.get('button').attributes('title')).toBe('Ativar avisos recorrentes quando Pão voltar')
  })

  it('captures the 18+ disclosure before login and preserves product context', async () => {
    await setAuthenticated(false)
    Object.assign(mocks.route, { path: '/menu', query: { categoria: 'paes' }, hash: '#fornada' })
    mocks.fetch.mockResolvedValue({ intent_ref: 'intent-opaque' })
    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão' })

    await wrapper.get('button').trigger('click')
    await nextTick()
    expect(mocks.fetch).not.toHaveBeenCalled()
    const form = document.body.querySelector<HTMLFormElement>('form')
    await new DOMWrapper(form!).trigger('submit')
    expect(mocks.fetch).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('Confirme que você tem 18 anos ou mais.')

    await acceptDisclosure()

    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(mocks.fetch.mock.calls[0]?.[0]).toContain('/availability/PAO/notify/intent/')
    expect(mocks.fetch.mock.calls[0]?.[1]).toMatchObject({ method: 'POST', body: { adult_declared: true } })
    expect(mocks.navigate).toHaveBeenCalledWith(
      `/entrar?next=${encodeURIComponent('/menu?categoria=paes&aviso=PAO&aviso_intent=intent-opaque#fornada')}`
    )
  })

  it('resumes a valid pre-login intent automatically without asking twice', async () => {
    await setAuthenticated(true)
    Object.assign(mocks.route, {
      path: '/menu',
      query: { categoria: 'paes', aviso: 'PAO', aviso_intent: 'intent-opaque' },
      hash: '#fornada'
    })
    mocks.fetch.mockResolvedValue({ management_url: '/gerenciar-aviso#capability' })
    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão' })
    await flush()

    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(mocks.fetch.mock.calls[0]?.[1]).toMatchObject({ method: 'POST', body: { intent_ref: 'intent-opaque' } })
    expect(document.body.querySelector('[data-stock-notify-sheet]')).toBeNull()
    expect(mocks.replace).toHaveBeenCalledWith({ path: '/menu', query: { categoria: 'paes' }, hash: '#fornada' })
    expect(wrapper.text()).toBe('Anotado')
    expect(wrapper.get('a').attributes('href')).toBe('/gerenciar-aviso#capability')
  })

  it('does not present a paused or cancelled replay as a new active opt-in', async () => {
    await setAuthenticated(true)
    Object.assign(mocks.route, { query: { aviso: 'PAO', aviso_intent: 'completed-intent' } })
    mocks.fetch.mockResolvedValue({ active: false })
    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão' })
    await flush()

    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(mocks.fetch.mock.calls[0]?.[1]?.body).toEqual({ intent_ref: 'completed-intent' })
    expect(mocks.replace).toHaveBeenCalledWith({ path: '/menu', query: {}, hash: '' })
    expect(wrapper.text()).toContain('Me avise sempre')
    expect(wrapper.text()).not.toContain('Anotado')
  })

  it('never falls back from a forged intent to an ordinary subscription', async () => {
    await setAuthenticated(true)
    Object.assign(mocks.route, { query: { aviso: 'PAO', aviso_intent: 'forged' } })
    mocks.fetch.mockRejectedValue(Object.assign(new Error('400'), {
      data: { detail: 'Este pedido de aviso expirou.', field: 'intent_ref' }
    }))
    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão' })
    await flush()

    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(mocks.fetch.mock.calls[0]?.[1]?.body).toEqual({ intent_ref: 'forged' })
    expect(mocks.replace).not.toHaveBeenCalledWith({ path: '/menu', query: {}, hash: '' })
    expect(wrapper.text()).toContain('Tentar ativar aviso')

    await wrapper.get('button').trigger('click')
    await nextTick()
    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(mocks.replace).toHaveBeenCalledWith({ path: '/menu', query: {}, hash: '' })
    expect(document.body.querySelector('[data-stock-notify-sheet]')).not.toBeNull()
  })

  it('treats a known minor as terminal and clears the stale intention', async () => {
    await setAuthenticated(true)
    Object.assign(mocks.route, { query: { aviso: 'PAO', aviso_intent: 'intent-minor' } })
    mocks.fetch.mockRejectedValue(Object.assign(new Error('400'), {
      data: { detail: 'Disponível somente para pessoas com 18 anos ou mais.', field: 'birthday' }
    }))
    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão' })
    await flush()

    expect(wrapper.text()).toContain('Disponível somente para pessoas com 18 anos ou mais.')
    expect(mocks.replace).toHaveBeenCalledWith({ path: '/menu', query: {}, hash: '' })
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  })

  it('requires an explicit declaration for an ordinary authenticated opt-in', async () => {
    await setAuthenticated(true)
    mocks.fetch.mockResolvedValue({ management_url: '/gerenciar-aviso#capability' })
    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão' })

    await wrapper.get('button').trigger('click')
    await nextTick()
    expect(mocks.fetch).not.toHaveBeenCalled()
    await acceptDisclosure()

    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(mocks.fetch.mock.calls[0]?.[1]?.body).toEqual({ adult_declared: true })
    expect(wrapper.text()).toBe('Anotado')
  })

  it('opens the consent sheet automatically for a legacy login return without proof', async () => {
    await setAuthenticated(true)
    Object.assign(mocks.route, { query: { aviso: 'PAO' } })
    await mountStockNotify({ sku: 'PAO', name: 'Pão' })
    await flush()

    expect(mocks.fetch).not.toHaveBeenCalled()
    expect(document.body.querySelector('[data-stock-notify-sheet]')).not.toBeNull()
  })

  it('keeps a product-specific accessible label before subscription', async () => {
    await setAuthenticated(false)
    const wrapper = await mountStockNotify({ sku: 'PAO', name: 'Pão', pill: true })
    expect(wrapper.get('button').attributes('aria-label')).toBe('Ativar avisos recorrentes quando Pão voltar')
  })
})
