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
  quote: {
    qty: '1',
    listing_ref: 'web',
    list_unit_price_q: 0,
    list_line_total_q: 0,
    final_unit_price_q: 0,
    final_line_total_q: 0,
    adjustments: []
  },
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
  it('explica a recorrência do aviso na listagem, antes de abrir o consentimento', async () => {
    const wrapper = await mountSuspended(ProductListItem, {
      props: { item: { ...item, availability: 'unavailable', is_notifiable: true } },
      global: { stubs: { StockNotifyButton: true } }
    })

    expect(wrapper.get('[data-stock-notify-recurrence]').text()).toBe('Avisos recorrentes pelo WhatsApp')
    expect(wrapper.get('stock-notify-button-stub').attributes('pill')).toBeDefined()
    wrapper.unmount()
  })

  it('não promete aviso antes de confirmar a disponibilidade nem para item não notificável', async () => {
    for (const props of [{ item, pending: false }, { item: { ...item, is_notifiable: true }, pending: true }]) {
      const wrapper = await mountSuspended(ProductListItem, { props, global: { stubs: { StockNotifyButton: true, CartQuantityAction: true } } })
      expect(wrapper.find('[data-stock-notify-recurrence]').exists()).toBe(false)
      wrapper.unmount()
    }
  })

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
