import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick, ref } from 'vue'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import ProductRecommendations from '~/components/ProductRecommendations.vue'
import { CROSS_SELL_LIMIT, RECOMMENDATIONS_ROOT_MARGIN } from '~/presentation/product'
import type { CatalogItemProjection, ProductRecommendationsResponse } from '~/types/shopman'

const mocks = vi.hoisted(() => ({
  execute: vi.fn(),
  clear: vi.fn(),
  observerOptions: [] as Array<Record<string, unknown>>,
  intersect: null as unknown as (entries: Array<{ isIntersecting: boolean }>) => void
}))

vi.mock('@vueuse/core', async importOriginal => ({
  ...await importOriginal<typeof import('@vueuse/core')>(),
  useIntersectionObserver: (_target: unknown, callback: typeof mocks.intersect, options?: Record<string, unknown>) => {
    mocks.intersect = callback
    if (options) mocks.observerOptions.push(options)
    return { stop: vi.fn() }
  }
}))

// O estado do fetch é dirigido pelo teste: é ele que diz se a seção ainda está
// reservando altura (idle/pending) ou se já pode encolher (success/error).
const data = ref<ProductRecommendationsResponse | null>(null)
const status = ref<'idle' | 'pending' | 'success' | 'error'>('idle')
const error = ref<Error | null>(null)

mockNuxtImport('useFetch', () => () => ({ data, status, error, execute: mocks.execute, clear: mocks.clear }))

const item: CatalogItemProjection = {
  sku: 'CROISSANT',
  slug: 'croissant',
  name: 'Croissant',
  short_description: 'Manteiga francesa',
  image_url: null,
  category: 'Pães',
  tags: [],
  search_terms: [],
  quote: {
    qty: '1',
    listing_ref: 'web',
    list_unit_price_q: 700,
    list_line_total_q: 700,
    final_unit_price_q: 700,
    final_line_total_q: 700,
    adjustments: []
  },
  unit_weight_label: null,
  availability: 'available',
  availability_label: '',
  can_add_to_cart: true,
  dietary_info: [],
  is_new: false,
  is_featured: false,
  qty_in_cart: 0,
  available_qty: null,
  allergens: [],
  is_paused: false,
  is_notifiable: false,
  is_notify_subscribed: false,
  is_favorite: false,
  dietary_warnings: [],
  category_color: null,
  category_icon: null
}

function withItems (skus: string[]): ProductRecommendationsResponse {
  return {
    recommendations: {
      sku: 'PAO-FRANCES',
      heading: 'Você também pode gostar',
      items: skus.map(sku => ({ ...item, sku, slug: sku.toLowerCase() }))
    }
  } as ProductRecommendationsResponse
}

describe('recomendações por proximidade da seção', () => {
  beforeEach(() => {
    mocks.execute.mockClear()
    mocks.clear.mockClear()
    mocks.observerOptions.length = 0
    data.value = null
    status.value = 'idle'
    error.value = null
  })

  it('não bloqueia a PDP e só lê ao se aproximar, inclusive depois de trocar SKU', async () => {
    const wrapper = await mountSuspended(ProductRecommendations, { props: { sku: 'A' } })
    expect(mocks.execute).not.toHaveBeenCalled()
    mocks.intersect([{ isIntersecting: false }])
    expect(mocks.execute).not.toHaveBeenCalled()
    mocks.intersect([{ isIntersecting: true }])
    expect(mocks.execute).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ sku: 'B' })
    await nextTick()
    expect(mocks.clear).toHaveBeenCalledTimes(1)
    expect(mocks.execute).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('só antecipa 0px: a leitura começa quando a seção entra na viewport', async () => {
    const wrapper = await mountSuspended(ProductRecommendations, { props: { sku: 'A' } })

    // 240px fazia o request partir com scrollY=0 numa viewport de 844px.
    expect(RECOMMENDATIONS_ROOT_MARGIN).toBe('0px')
    expect(mocks.observerOptions).toHaveLength(1)
    expect(mocks.observerOptions[0]!.rootMargin).toBe(RECOMMENDATIONS_ROOT_MARGIN)

    wrapper.unmount()
  })

  it('reserva a altura do rail desde o primeiro paint, antes de qualquer leitura', async () => {
    const wrapper = await mountSuspended(ProductRecommendations, { props: { sku: 'A' } })

    const skeleton = wrapper.find('[data-product-recommendations-skeleton]')
    expect(skeleton.exists()).toBe(true)
    // A reserva desenha o TETO do rail: com o mesmo número de cards que o
    // servidor pode devolver, a seção pronta nunca é mais alta que o placeholder.
    expect(CROSS_SELL_LIMIT).toBe(4)
    expect(skeleton.findAll('[data-product-recommendations-skeleton-card]')).toHaveLength(CROSS_SELL_LIMIT)
    // Antes de entrar na viewport não há leitura em curso: a reserva é muda.
    expect(skeleton.attributes('aria-hidden')).toBe('true')
    expect(wrapper.find('[role="status"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('anuncia o carregamento e troca o placeholder pela seção quando os itens chegam', async () => {
    status.value = 'pending'
    const wrapper = await mountSuspended(ProductRecommendations, { props: { sku: 'A' } })

    const loading = wrapper.find('[data-product-recommendations-skeleton]')
    expect(loading.exists()).toBe(true)
    expect(loading.attributes('role')).toBe('status')
    expect(loading.attributes('aria-busy')).toBe('true')
    expect(loading.attributes('aria-hidden')).toBeUndefined()

    data.value = withItems(['CROISSANT', 'BAGUETE'])
    status.value = 'success'
    await nextTick()

    expect(wrapper.find('[data-product-recommendations-skeleton]').exists()).toBe(false)
    const section = wrapper.find('[data-product-cross-sell]')
    expect(section.exists()).toBe(true)
    expect(section.findAll('[data-product-list-item]')).toHaveLength(2)
    expect(wrapper.text()).toContain('Você também pode gostar')

    wrapper.unmount()
  })

  it('mantém a altura reservada quando a resposta não traz sugestões', async () => {
    // O caso que o CLS cobra: a reserva é do TAMANHO DO TETO do rail, e uma
    // resposta com menos cards encolheria a seção. Encolher puxa para cima o que
    // está abaixo (footer incluído), e isso também é layout shift. O piso fica.
    const restoreRect = stubRailHeight(751)
    status.value = 'pending'
    const wrapper = await mountSuspended(ProductRecommendations, { props: { sku: 'A' } })

    data.value = withItems([])
    status.value = 'success'
    await nextTick()

    expect(wrapper.find('[data-product-recommendations-skeleton]').exists()).toBe(false)
    expect(wrapper.find('[data-product-cross-sell]').exists()).toBe(false)
    expect(wrapper.attributes('style')).toContain('min-height: 751px')

    wrapper.unmount()
    restoreRect()
  })

  it('congela a altura do placeholder antes de trocar o DOM pela seção', async () => {
    const restoreRect = stubRailHeight(751)
    status.value = 'pending'
    const wrapper = await mountSuspended(ProductRecommendations, { props: { sku: 'A' } })
    expect(wrapper.attributes('style') ?? '').not.toContain('min-height')

    data.value = withItems(['CROISSANT', 'BAGUETE'])
    status.value = 'success'
    await nextTick()

    // Dois cards ocupam ~320 px num piso de 751: sem o piso, o footer subiria.
    expect(wrapper.find('[data-product-cross-sell]').exists()).toBe(true)
    expect(wrapper.attributes('style')).toContain('min-height: 751px')

    wrapper.unmount()
    restoreRect()
  })
})

// O jsdom não tem layout: sem este stub a altura medida é 0 e o piso nunca é
// gravado. O valor é o que o Playwright mediu na PDP real em 390x844.
function stubRailHeight (height: number): () => void {
  const original = Element.prototype.getBoundingClientRect
  const spy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    if (this.hasAttribute?.('data-product-recommendations')) {
      return { height, width: 390, top: 0, left: 0, bottom: height, right: 390, x: 0, y: 0, toJSON: () => ({}) } as DOMRect
    }
    return original.call(this)
  })
  return () => spy.mockRestore()
}
