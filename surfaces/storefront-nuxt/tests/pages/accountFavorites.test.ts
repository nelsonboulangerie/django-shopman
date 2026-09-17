// `conta/favoritos` mostra o esgotado com a MESMA pílula do cardápio, e o sino
// segue o que o coração devolveu (Pablo, 17/09): favoritar um esgotado com
// opt-in de WhatsApp e maioridade provada anota o aviso, e o card vira
// "Anotado" sem esperar a próxima projeção. Sem essa base, continua "Me avise".
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'
import FavoritesPage from '~/pages/conta/favoritos.vue'
import type { CatalogItemProjection, FavoriteToggleResponse } from '~/types/shopman'

// `mockNuxtImport('useSonner')` não alcança o alias de `vue-sonner` neste harness
// (o import do composable continua o real); espiar o objeto real é o que prova.
let noted: ReturnType<typeof vi.spyOn>

function item (overrides: Partial<CatalogItemProjection> = {}): CatalogItemProjection {
  return {
    sku: 'PAO-FERMENTACAO',
    slug: 'PAO-FERMENTACAO',
    name: 'Pão de Fermentação',
    short_description: '',
    image_url: null,
    category: null,
    tags: [],
    search_terms: [],
    base_price_q: 1800,
    price_display: 'R$ 18,00',
    has_promotion: false,
    original_price_display: null,
    promotion_label: null,
    unit_weight_label: null,
    availability: 'unavailable',
    availability_label: 'Indisponível',
    can_add_to_cart: false,
    dietary_info: [],
    is_new: false,
    is_featured: false,
    qty_in_cart: 0,
    available_qty: 0,
    allergens: [],
    is_paused: false,
    is_notifiable: true,
    is_notify_subscribed: false,
    is_favorite: true,
    dietary_warnings: [],
    category_color: null,
    category_icon: null,
    ...overrides
  }
}

let served: CatalogItemProjection[] = []
let toggleResponse: FavoriteToggleResponse
registerEndpoint('/api/v1/account/favorites/', () => ({ items: served, copy: {} }))
registerEndpoint('/api/v1/account/favorites/PAO-FERMENTACAO/', { method: 'POST', handler: () => toggleResponse })
registerEndpoint('/api/v1/availability/PAO-FERMENTACAO/notify/', () => ({ active: true, management_url: '' }))

const mounted: Array<{ unmount: () => void }> = []

async function openFavorites (items: CatalogItemProjection[]) {
  served = items
  clearNuxtData()
  const page = await mountSuspended(FavoritesPage)
  mounted.push(page)
  await flushPromises()
  return page
}

function pill (page: Awaited<ReturnType<typeof openFavorites>>) {
  return page.find('[data-product-list-item] button, [data-product-list-item] a[aria-label*="Anotado"]')
}

describe('conta/favoritos — a pílula do aviso', () => {
  beforeEach(async () => {
    document.cookie = 'csrftoken=testtoken'
    noted = vi.spyOn(useSonner, 'success').mockImplementation(() => '' as never)
    const { useShopSession } = await import('~/composables/useShopSession')
    const session = useShopSession()
    session.reset()
    session.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana', customer_phone: '43999' })
    useState<Record<string, boolean>>('stock-notify-subscribed-overrides', () => ({})).value = {}
    useState<Record<string, boolean>>('shopman-favorites', () => ({})).value = {}
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
    vi.restoreAllMocks()
  })

  it('mostra "Me avise" no esgotado notificável sem aviso', async () => {
    const page = await openFavorites([item()])

    expect(page.text()).toContain('Indisponível')
    expect(pill(page).exists()).toBe(true)
    expect(pill(page).text()).toContain('Me avise')
    expect(page.text()).not.toContain('Anotado')
  })

  it('mostra "Anotado" quando a projeção traz o aviso', async () => {
    const page = await openFavorites([item({ is_notify_subscribed: true })])

    expect(page.text()).toContain('Anotado')
    expect(page.text()).not.toContain('Me avise')
  })

  it('não oferece sino para o item pausado', async () => {
    const page = await openFavorites([item({ is_paused: true, is_notifiable: false })])

    expect(page.text()).toContain('Indisponível')
    expect(page.text()).not.toContain('Me avise')
    expect(page.text()).not.toContain('Anotado')
  })

  it('vira "Anotado" na hora quando o coração anota o aviso', async () => {
    const page = await openFavorites([item()])
    expect(page.text()).toContain('Me avise')

    toggleResponse = { ok: true, is_favorite: true, is_notify_subscribed: true, stock_alert_noted: true }
    const { useFavoritesState } = await import('~/composables/useFavoritesState')
    await useFavoritesState().toggle('PAO-FERMENTACAO', false)
    await flushPromises()

    expect(page.text()).toContain('Anotado')
    expect(page.text()).not.toContain('Me avise')
    expect(noted).toHaveBeenCalledOnce()
    expect(String(noted.mock.calls[0]?.[0])).toContain('aviso ativo')
  })

  it('continua "Me avise" quando o favorito não tinha base para anotar', async () => {
    const page = await openFavorites([item()])

    toggleResponse = { ok: true, is_favorite: true, is_notify_subscribed: false, stock_alert_noted: false }
    const { useFavoritesState } = await import('~/composables/useFavoritesState')
    await useFavoritesState().toggle('PAO-FERMENTACAO', false)
    await flushPromises()

    expect(page.text()).toContain('Me avise')
    expect(page.text()).not.toContain('Anotado')
    expect(noted).not.toHaveBeenCalled()
  })
})
