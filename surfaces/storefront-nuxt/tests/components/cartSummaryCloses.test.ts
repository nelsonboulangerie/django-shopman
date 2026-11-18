// WP-L03 (decisão do dono 1, 16/11/2026): o preço fecha. A linha com promoção
// do produto mostra o total com desconto e o cheio riscado, com a palavra
// "antes"; o resumo abre pelo Subtotal que é a soma das linhas, diz quanto as
// promoções já abateram e só subtrai o que é do pedido (cupom, pontos).
import { describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import CartLineTotal from '~/components/CartLineTotal.vue'
import CartSummaryBreakdown from '~/components/CartSummaryBreakdown.vue'
import type { CartProjection } from '~/types/shopman'

function cart (overrides: Partial<CartProjection> = {}): CartProjection {
  return {
    items: [],
    items_count: 3,
    is_empty: false,
    empty_title: '',
    empty_message: '',
    subtotal_q: 2310,
    subtotal_display: 'R$ 23,10',
    original_subtotal_q: 2600,
    discount_total_q: 290,
    discount_total_display: 'R$ 2,90',
    has_discount: true,
    discount_lines: [
      { label: 'Cupom BEMVINDA', amount_q: 200, amount_display: 'R$ 2,00' },
      { label: 'Oferta do Croissant', amount_q: 90, amount_display: 'R$ 0,90' }
    ],
    lines_subtotal_q: 2510,
    lines_subtotal_display: 'R$ 25,10',
    promo_savings_q: 90,
    promo_savings_display: 'R$ 0,90',
    order_discount_lines: [{ label: 'Cupom BEMVINDA', amount_q: 200, amount_display: 'R$ 2,00' }],
    delivery_fee_q: null,
    delivery_fee_display: null,
    delivery_is_free: false,
    delivery_zone_error: false,
    delivery_distance_km: null,
    delivery_distance_display: null,
    grand_total_q: 2310,
    grand_total_display: 'R$ 23,10',
    loyalty_applied: false,
    group_savings_message: '',
    coupon_code: 'BEMVINDA',
    coupon_discount_q: 200,
    coupon_discount_display: 'R$ 2,00',
    coupon_zero_reason: '',
    coupon_missing_q: 0,
    coupon_missing_display: null,
    coupon_fulfillment_types: [],
    has_unavailable_items: false,
    has_awaiting_confirmation_items: false,
    has_ready_for_confirmation_items: false,
    unavailable_banner: '',
    awaiting_confirmation_notice: '',
    minimum_order_progress: null,
    delivery_minimum_progress: null,
    free_delivery_progress: null,
    upsell: null,
    actions: [],
    ...overrides
  } as CartProjection
}

describe('CartLineTotal', () => {
  it('com promoção: o total com desconto e o cheio riscado, com "antes"', async () => {
    const wrapper = await mountSuspended(CartLineTotal, {
      props: { line: { line_total_display: 'R$ 10,20', line_total_struck_display: 'R$ 12,00' } }
    })
    expect(wrapper.find('.shop-price').text()).toBe('R$ 10,20')
    const struck = wrapper.find('[data-line-total-struck]')
    expect(struck.text()).toBe('antes R$ 12,00')
    expect(struck.find('.line-through').text()).toBe('R$ 12,00')
  })

  it('sem promoção: um valor só, nada riscado', async () => {
    const wrapper = await mountSuspended(CartLineTotal, {
      props: { line: { line_total_display: 'R$ 12,00', line_total_struck_display: null } }
    })
    expect(wrapper.text()).toBe('R$ 12,00')
    expect(wrapper.find('[data-line-total-struck]').exists()).toBe(false)
  })
})

describe('CartSummaryBreakdown', () => {
  it('o Subtotal é a soma das linhas e a promoção não é subtraída de novo', async () => {
    const wrapper = await mountSuspended(CartSummaryBreakdown, { props: { cart: cart() } })
    const text = wrapper.text()

    expect(wrapper.find('[data-summary-subtotal]').text()).toContain('R$ 25,10')
    expect(wrapper.find('[data-summary-promo-savings]').text()).toBe('Já com R$ 0,90 de desconto em promoções.')
    expect(text).toContain('Cupom BEMVINDA')
    expect(text).toContain('- R$ 2,00')
    expect(text).not.toContain('Oferta do Croissant')
    expect(text).toContain('R$ 23,10')
  })

  it('sem desconto nenhum: Subtotal e Total, sem nota e sem linha de desconto', async () => {
    const wrapper = await mountSuspended(CartSummaryBreakdown, {
      props: {
        cart: cart({
          has_discount: false,
          discount_lines: [],
          order_discount_lines: [],
          promo_savings_q: 0,
          promo_savings_display: null,
          lines_subtotal_q: 2600,
          lines_subtotal_display: 'R$ 26,00',
          grand_total_q: 2600,
          grand_total_display: 'R$ 26,00'
        })
      }
    })
    expect(wrapper.find('[data-summary-promo-savings]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('- R$')
  })
})
