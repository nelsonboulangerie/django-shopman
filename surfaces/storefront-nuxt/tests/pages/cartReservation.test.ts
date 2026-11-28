import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'

import CartPage from '~/pages/sacola.vue'
import type { CartItemProjection, CartProjection } from '~/types/shopman'
import { announceStoreChange, resetLiveStoreForTests } from '~/composables/useLiveStore'

// Reserva com prazo à vista (WP-L11): a sacola diz até quando guarda os itens, e
// quando o prazo passa com a cliente na tela ela relê a sacola sozinha.

function line (overrides: Partial<CartItemProjection> = {}): CartItemProjection {
  return {
    line_id: 'line-1',
    sku: 'CRO',
    name: 'Croissant',
    qty: 2,
    unit_price_q: 900,
    total_price_q: 1800,
    price_display: 'R$ 9,00',
    line_total_display: 'R$ 18,00',
    line_total_struck_display: null,
    list_price_q: 900,
    image_url: null,
    discount_label: null,
    promo_price_display: null,
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
    earlier_available_date: null,
    notes: '',
    promise: null,
    ...overrides
  }
}

function cart (overrides: Partial<CartProjection> = {}): CartProjection {
  return {
    items: [line()],
    items_count: 2,
    is_empty: false,
    empty_title: '',
    empty_message: '',
    summary_pending: false,
    subtotal_q: 1800,
    subtotal_display: 'R$ 18,00',
    original_subtotal_q: 1800,
    discount_total_q: 0,
    discount_total_display: 'R$ 0,00',
    has_discount: false,
    discount_lines: [],
    lines_subtotal_q: 1800,
    lines_subtotal_display: 'R$ 18,00',
    promo_savings_q: 0,
    promo_savings_display: null,
    order_discount_lines: [],
    group_savings_message: '',
    delivery_fee_q: null,
    delivery_fee_display: null,
    delivery_is_free: false,
    delivery_zone_error: false,
    delivery_distance_km: null,
    delivery_distance_display: null,
    grand_total_q: 1800,
    grand_total_display: 'R$ 18,00',
    loyalty_applied: false,
    coupon_code: null,
    coupon_discount_q: null,
    coupon_discount_display: null,
    coupon_zero_reason: '',
    coupon_missing_q: 0,
    coupon_missing_display: null,
    coupon_fulfillment_types: [],
    has_unavailable_items: false,
    has_awaiting_confirmation_items: false,
    has_ready_for_confirmation_items: false,
    unavailable_banner: '',
    awaiting_confirmation_notice: '',
    reserved_until_iso: null,
    reserved_until_display: null,
    reservation_lapsed_display: null,
    minimum_order_progress: null,
    delivery_minimum_progress: null,
    free_delivery_progress: null,
    upsell: null,
    actions: [
      { ref: 'checkout', kind: 'navigate', label: 'Finalizar pedido', priority: 'primary', enabled: true, reason: '', method: 'GET', href: '/finalizar' }
    ],
    revision: 1,
    ...overrides
  } as CartProjection
}

function inMinutes (minutes: number, from = Date.now()): string {
  return new Date(from + minutes * 60_000).toISOString()
}

let served: Array<() => CartProjection> = []
let reads = 0
// O relógio do servidor vem no envelope da leitura da sacola; por padrão, igual ao do aparelho.
let serverNow: () => number = () => Date.now()
registerEndpoint('/api/v1/storefront/cart/', () => {
  const answer = served[Math.min(reads, served.length - 1)]!
  reads += 1
  return { cart: answer(), server_now_iso: new Date(serverNow()).toISOString() }
})

async function openCart (...answers: Array<() => CartProjection>) {
  served = answers
  reads = 0
  clearNuxtData()
  // A sacola que a página encontra no estado é a que o shell trouxe.
  useState('storefront-cart').value = answers[0]!()
  useState('storefront-cart-clock-offset').value = 0
  const page = await mountSuspended(CartPage)
  await vi.waitFor(() => expect(reads).toBeGreaterThan(0))
  await flushPromises()
  return page
}

let mounted: Awaited<ReturnType<typeof openCart>> | null = null
beforeEach(() => { document.cookie = 'csrftoken=local-test'; serverNow = () => Date.now() })
afterEach(() => { mounted?.unmount(); mounted = null; resetLiveStoreForTests() })

describe('sacola: reserva com prazo à vista', () => {
  it('diz até quando guarda os itens, no alto da sacola, sem cronômetro', async () => {
    const page = await openCart(() => cart({ reserved_until_iso: inMinutes(18), reserved_until_display: '19h18' }))
    mounted = page

    const notice = page.find('[data-cart-reservation="held"]')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toBe('Guardamos seus itens até 19h18.')
    // Uma linha calma: a hora, e nenhuma contagem regressiva.
    expect(notice.text()).not.toMatch(/\d{1,2}:\d{2}/)
    // No alto, no bloco do título; sem a linha do "fica pronto", ocupa o lugar sozinha.
    expect(notice.element.parentElement?.querySelector('h1')?.textContent).toBe('Sua sacola')
    expect(page.find('[data-cart-ready-line]').exists()).toBe(false)
    // É a única linha de prazo da tela: nada sobrou abaixo do resumo.
    expect(page.findAll('[data-cart-reservation]')).toHaveLength(1)
    expect(page.find('aside [data-cart-reservation]').exists()).toBe(false)
  })

  it('fica logo depois de "Seu pedido fica pronto", com o mesmo texto de apoio', async () => {
    const tomorrowBatch = line({
      promise: { kind: 'batch', date: '2099-01-01', ready_at: '15:00', day_label: 'amanhã, sexta', text: 'Fica pronto amanhã, sexta, a partir das 15h' }
    })
    const page = await openCart(() => cart({ items: [tomorrowBatch], reserved_until_iso: inMinutes(18), reserved_until_display: '19h18' }))
    mounted = page

    const ready = page.find('[data-cart-ready-line]')
    const notice = page.find('[data-cart-reservation="held"]')
    expect(ready.exists()).toBe(true)
    expect(ready.text()).toContain('Seu pedido fica pronto')
    // A linha do prazo é a irmã seguinte, com as mesmas classes de texto.
    expect(ready.element.nextElementSibling).toBe(notice.element)
    expect(notice.classes().sort()).toEqual(ready.classes().sort())
    expect(notice.find('svg, span, i').classes()).toEqual(ready.find('svg, span, i').classes())
    expect(page.findAll('[data-cart-reservation]')).toHaveLength(1)
  })

  it('conta o prazo pelo relógio do servidor: aparelho adiantado não vence a reserva', async () => {
    // Para o servidor é uma hora mais cedo do que o aparelho diz. Pelo aparelho o
    // prazo (daqui a 20 min no relógio do servidor) já teria passado há 40.
    serverNow = () => Date.now() - 60 * 60_000
    const page = await openCart(() => cart({
      reserved_until_iso: inMinutes(20, serverNow()),
      reserved_until_display: '19h18'
    }))
    mounted = page

    await vi.waitFor(() => expect(page.find('[data-cart-reservation="held"]').exists()).toBe(true))
    // Deixa o relógio da tela bater pelo menos uma vez.
    await new Promise(resolve => setTimeout(resolve, 1200))
    expect(page.find('[data-cart-reservation="held"]').exists()).toBe(true)
    expect(page.find('[data-cart-reservation="lapsed"]').exists()).toBe(false)
  })

  it('sacola só com item de fornada futura não promete hora', async () => {
    const page = await openCart(() => cart())
    mounted = page

    expect(page.find('[data-cart-reservation]').exists()).toBe(false)
  })

  it('quem abre a sacola depois do prazo lê que a reserva venceu, já na carga (#2767)', async () => {
    const page = await openCart(() => cart({ reservation_lapsed_display: '18/11 às 19h18' }))
    mounted = page
    await flushPromises()

    const notice = page.find('[data-cart-reservation="lapsed"]')
    expect(notice.text()).toBe('A reserva valia até 18/11 às 19h18 e já venceu. A sacola mostra o que continua disponível.')
    expect(page.findAll('[data-cart-reservation]')).toHaveLength(1)
    expect(page.text()).toContain('Croissant')
  })

  it('vencido o prazo, relê a sacola sozinha e diz o que houve', async () => {
    const held = cart({ reserved_until_iso: new Date(Date.now() + 1500).toISOString(), reserved_until_display: '19h18' })
    const page = await openCart(
      () => held,
      // Depois do prazo o servidor não tem mais reserva com relógio: a linha segue na sacola.
      () => cart({ reserved_until_iso: null, reserved_until_display: null })
    )
    mounted = page
    expect(page.find('[data-cart-reservation="held"]').exists()).toBe(true)
    const readsBefore = reads

    await vi.waitFor(() => {
      expect(page.find('[data-cart-reservation="lapsed"]').exists()).toBe(true)
    }, { timeout: 6000, interval: 100 })
    await vi.waitFor(() => expect(reads).toBeGreaterThan(readsBefore), { timeout: 3000 })
    await flushPromises()

    const notice = page.find('[data-cart-reservation="lapsed"]')
    expect(notice.text()).toBe('A reserva valia até 19h18 e já venceu. A sacola mostra o que continua disponível.')
    expect(notice.attributes('role')).toBe('status')
    // O prazo vencido fica no mesmo lugar da hora: no alto, e uma linha só.
    expect(notice.element.parentElement?.querySelector('h1')?.textContent).toBe('Sua sacola')
    expect(page.findAll('[data-cart-reservation]')).toHaveLength(1)
    expect(page.find('aside [data-cart-reservation]').exists()).toBe(false)
    // A sacola continua lá, com o item.
    expect(page.text()).toContain('Croissant')
    // E não fica relendo em laço.
    const readsAfter = reads
    await new Promise(resolve => setTimeout(resolve, 2200))
    expect(reads).toBe(readsAfter)
  }, 20_000)
})

describe('sacola: a vitrine muda com a sacola aberta (#2785)', () => {
  it('o aviso da vitrine relê as linhas, sem esperar o próximo gesto', async () => {
    const page = await openCart(
      () => cart(),
      // Outra cliente levou: da linha de 2, sobrou 1.
      () => cart({ items: [line({ is_available: false, available_qty: 1, availability_warning: 'Apenas 1 unidade disponível' })] })
    )
    mounted = page
    const before = reads

    announceStoreChange('poll')

    await vi.waitFor(() => expect(reads).toBeGreaterThan(before))
    await vi.waitFor(() => expect(page.text()).toContain('Usar 1 disponível'))
  })

  it('a recusa do servidor não relê a sacola outra vez: a mutação recusada já releu', async () => {
    const page = await openCart(() => cart())
    mounted = page
    const before = reads

    announceStoreChange('refusal')
    await flushPromises()

    expect(reads).toBe(before)
  })
})
