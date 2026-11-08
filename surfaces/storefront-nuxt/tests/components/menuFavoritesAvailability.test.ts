import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import MenuFavoritesShelf from '~/components/MenuFavoritesShelf.vue'
import type { CatalogItemProjection } from '~/types/shopman'

function favorite (sku: string, availability: CatalogItemProjection['availability'], warnings: string[] = []): CatalogItemProjection {
  return {
    sku, slug: sku, name: sku, short_description: '', image_url: null,
    category: null, tags: [], search_terms: [], dietary_info: [], is_new: false,
    quote: { qty: '1', listing_ref: 'web', list_unit_price_q: 800, list_line_total_q: 800, final_unit_price_q: 800, final_line_total_q: 800, adjustments: [] },
    unit_weight_label: null, availability, availability_label: availability,
    can_add_to_cart: availability !== 'unavailable', available_qty: 1,
    dietary_warnings: warnings, allergens: [], qty_in_cart: 0,
    is_favorite: true, is_notifiable: false, is_paused: false
  } as CatalogItemProjection
}

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)

const response = { items: [
  favorite('ESGOTADO', 'unavailable'),
  favorite('PRONTO', 'available'),
  favorite('FORNADA', 'planned_ok'),
  favorite('COM-GLUTEN', 'available', ['Contém glúten'])
] }

const mounted: Array<{ unmount: () => void }> = []
beforeEach(async () => {
  fetchMock.mockReset().mockResolvedValue(response)
  const { useShopSession } = await import('~/composables/useShopSession')
  useShopSession().reset()
})
afterEach(() => { for (const component of mounted.splice(0)) component.unmount() })

describe('favoritos no cardápio seguem os filtros da página', () => {
  it('tira o esgotado e preserva a fornada; desligar restaura os favoritos', async () => {
    const shelf = await mountSuspended(MenuFavoritesShelf, { props: { active: true, availableOnly: true } })
    mounted.push(shelf)
    const { useShopSession } = await import('~/composables/useShopSession')
    useShopSession().setFromAuthSession({ is_authenticated: true, customer_name: 'Ana', customer_phone: '43999' })
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/account/favorites/', { credentials: 'include' })
    await vi.waitFor(() => expect(shelf.text()).toContain('PRONTO'))
    expect(shelf.text()).not.toContain('ESGOTADO')
    expect(shelf.text()).toContain('PRONTO')
    expect(shelf.text()).toContain('FORNADA')
    await shelf.setProps({ availableOnly: false })
    expect(shelf.text()).toContain('ESGOTADO')
  })

  it('combina disponibilidade com preferências sem alterar a lista recebida', async () => {
    const shelf = await mountSuspended(MenuFavoritesShelf, { props: { active: true, availableOnly: true, hideDietaryWarnings: true } })
    mounted.push(shelf)
    const { useShopSession } = await import('~/composables/useShopSession')
    useShopSession().setFromAuthSession({ is_authenticated: true, customer_name: 'Ana', customer_phone: '43999' })
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/account/favorites/', { credentials: 'include' })
    await vi.waitFor(() => expect(shelf.text()).toContain('PRONTO'))
    expect(shelf.text()).not.toContain('COM-GLUTEN')
    expect(shelf.text()).not.toContain('ESGOTADO')
    expect(shelf.text()).toContain('PRONTO')
    await shelf.setProps({ availableOnly: false, hideDietaryWarnings: false })
    expect(shelf.text()).toContain('COM-GLUTEN')
    expect(shelf.text()).toContain('ESGOTADO')
  })
})
