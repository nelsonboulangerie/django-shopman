import { describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import ProductListItem from '~/components/ProductListItem.vue'
import type { CatalogItemProjection } from '~/types/shopman'

const item: CatalogItemProjection = {
  sku: 'PAO',
  slug: 'pao',
  name: 'Pão',
  short_description: 'Fermentação natural',
  image_url: null,
  category: 'Pães',
  tags: [],
  search_terms: [],
  base_price_q: 0,
  price_display: '',
  has_promotion: false,
  original_price_display: null,
  promotion_label: null,
  unit_weight_label: '500 g',
  availability: 'available',
  availability_label: '',
  can_add_to_cart: false,
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

describe('ProductListItem com quadro estrutural Continuum', () => {
  it('mostra o produto sem inventar preço, estoque ou gesto de compra', async () => {
    const wrapper = await mountSuspended(ProductListItem, {
      props: { item, pending: true }
    })

    expect(wrapper.text()).toContain('Pão')
    expect(wrapper.find('[aria-label="Confirmando preço e disponibilidade"]').exists()).toBe(true)
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Indisponível')
  })
})
