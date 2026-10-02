// Observação por item na sacola: convite discreto, campo com teto de 280
// caracteres e o texto salvo só depois que o servidor o gravou na linha.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import CartLineNote from '~/components/CartLineNote.vue'
import type { CartItemProjection } from '~/types/shopman'

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return fn
})

function line (overrides: Partial<CartItemProjection> = {}): CartItemProjection {
  return {
    line_id: 'L-1',
    sku: 'PAO-GERGELIM',
    name: 'Pão de gergelim',
    qty: 2,
    unit_price_q: 900,
    total_price_q: 1800,
    price_display: 'R$ 9,00',
    total_display: 'R$ 18,00',
    image_url: null,
    original_price_display: null,
    discount_label: null,
    is_available: true,
    availability_warning: null,
    available_qty: null,
    is_notifiable: false,
    is_notify_subscribed: false,
    is_made_to_order: false,
    made_to_order_label: '',
    is_awaiting_confirmation: false,
    is_ready_for_confirmation: false,
    confirmation_deadline_iso: null,
    confirmation_deadline_display: null,
    planned_for_date: null,
    planned_for_notice: null,
    notes: '',
    ...overrides
  }
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe('CartLineNote', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    fetchMock.mockReset()
  })

  it('abre o campo, limita a 280 caracteres e salva na linha do SKU', async () => {
    fetchMock.mockResolvedValue({ cart: { items: [line({ notes: 'sem gergelim' })] } })
    const wrapper = await mountSuspended(CartLineNote, { props: { line: line() } })

    await wrapper.get('[data-cart-line-note-open]').trigger('click')
    const input = wrapper.get('[data-cart-line-note-input]')
    expect(input.attributes('maxlength')).toBe('280')
    await input.setValue('sem gergelim')
    await wrapper.get('[data-cart-line-note-save]').trigger('click')
    await flush()

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(String(fetchMock.mock.calls[0]![0])).toContain('/api/v1/cart/skus/PAO-GERGELIM/notes/')
    expect(fetchMock.mock.calls[0]![1]).toMatchObject({ method: 'PUT', body: { notes: 'sem gergelim' } })
    expect(wrapper.find('[data-cart-line-note-input]').exists()).toBe(false)
  })

  it('mostra a observação salva com o rótulo curto', async () => {
    const wrapper = await mountSuspended(CartLineNote, { props: { line: line({ notes: 'bem assado' }) } })

    expect(wrapper.get('[data-cart-line-note-text]').text()).toContain('Obs.: bem assado')
  })

  it('não oferece observação numa linha que ainda não chegou ao servidor', async () => {
    const wrapper = await mountSuspended(CartLineNote, { props: { line: line({ line_id: 'optimistic-PAO-GERGELIM' }) } })

    expect(wrapper.find('[data-cart-line-note]').exists()).toBe(false)
  })
})
