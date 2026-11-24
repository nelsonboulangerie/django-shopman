// EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
// OC-33 B1: "Para quando?" antes da lista, a sacola e o checkout já no dia. Quem
// decide a versão é o servidor (shell `experience`); a página só muda a PERGUNTA
// e a forma de dizer. A: idêntica ao main (sem pergunta, sem barra, sem dia no
// Adicionar). B: pergunta o dia, lê o cardápio daquele dia (`?date=`), manda o dia
// com o Adicionar, a sacola diz o dia e o checkout abre nele (X10, WCAG 3.3.7).
// Disponibilidade, promessa e frase do dia vêm do servidor (X13).
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'
import { getQuery, readBody, setResponseStatus } from 'h3'

import catalogDayContractJson from '../../../../contracts/projections/storefront_catalog_day.json'
import catalogContractJson from '../../../../contracts/projections/storefront_catalog.json'
import MenuPage from '~/pages/menu.vue'
import CartPage from '~/pages/sacola.vue'
import CheckoutPage from '~/pages/finalizar.vue'
import ProductListItem from '~/components/ProductListItem.vue'
import { MENU_DAY_KEY } from '~/composables/useMenuDay'
import { STOREFRONT_SHELL_KEY } from '~/composables/useStorefrontShell'
import type { CartProjection, CatalogItemProjection, CatalogProjection, CheckoutProjection, ShellResponse } from '~/types/shopman'

// O contrato guarda datas relativas; aqui viram a terça, 24/11/2026.
function withRealDates<T> (value: T): T {
  const map: Record<string, string> = { '<today>': '2026-11-24', '<tomorrow>': '2026-11-25' }
  const dates = ['2026-11-26', '2026-11-27', '2026-11-28']
  let index = 0
  return JSON.parse(JSON.stringify(value), (key, raw) => {
    if (raw === '<date>' && key === 'max_date') return '2026-12-24'
    if (raw === '<date>') return dates[Math.min(index++, dates.length - 1)]
    return typeof raw === 'string' && raw in map ? map[raw] : raw
  }) as T
}

const TODAY_CATALOG = withRealDates(catalogContractJson as unknown as CatalogProjection)
const DAY_CATALOG = withRealDates(catalogDayContractJson as unknown as CatalogProjection)

const catalogQueries: Array<Record<string, unknown>> = []
registerEndpoint('/api/v1/storefront/catalog/', (event) => {
  const query = getQuery(event)
  catalogQueries.push(query)
  return { catalog: query.date ? DAY_CATALOG : TODAY_CATALOG }
})

// O "Trocar" (PUT cart/day/): a primeira tentativa esbarra na Tabatière; com `without`, passa.
const dayCalls: Array<Record<string, unknown>> = []
registerEndpoint('/api/v1/cart/day/', {
  method: 'PUT',
  handler: async (event) => {
    const body = await readBody(event)
    dayCalls.push(body)
    if (!(body.without || []).length) {
      // O corpo do 409 é o da API (Django), não o envelope de erro do h3.
      setResponseStatus(event, 409)
      return {
        error_code: 'cart_day_change_refused',
        title: 'Tabatière não está disponível para quinta, 26/11',
        detail: 'Você pode seguir para quinta, 26/11 sem esse item, ou manter o dia que tinha.',
        date: '2026-11-26',
        date_label: 'quinta, 26/11',
        items: [{ ref: 'TABAT', sku: 'TABAT', name: 'Tabatière', requested_qty: 1, available_qty: 0 }]
      }
    }
    return { cart: { ...useState<CartProjection>('storefront-cart').value, day: { date: '2026-11-26', label: 'quinta, 26/11' } } }
  }
})

function setShell (variant?: 'a' | 'b') {
  useNuxtApp().payload.data[STOREFRONT_SHELL_KEY] = {
    shell: { experience: variant ? [{ ref: 'cardapio-dia-primeiro', variant }] : [] },
    cart: {}
  } as unknown as ShellResponse
}

const mounted: Array<{ unmount: () => void }> = []

async function openMenu (variant?: 'a' | 'b') {
  clearNuxtData()
  setShell(variant)
  useState('shopman-menu-day').value = ''
  catalogQueries.length = 0
  const page = await mountSuspended(MenuPage, { global: { stubs: { MenuFavoritesShelf: true } } })
  mounted.push(page)
  await vi.waitFor(() => expect(page.find('[data-menu-day-picker], [data-menu-results]').exists()).toBe(true))
  await flushPromises()
  return page
}

afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount()
  useState('shopman-menu-day').value = ''
  setShell()
})

describe('cardápio: "Para quando?" antes da lista (OC-33 B1)', () => {
  it('A (padrão, sem experimento): a lista de sempre, sem pergunta, sem barra, sem data na leitura', async () => {
    const page = await openMenu()
    expect(page.find('[data-menu-day-picker]').exists()).toBe(false)
    expect(page.find('[data-menu-day-bar]').exists()).toBe(false)
    expect(page.find('[data-menu-results]').exists()).toBe(true)
    expect(catalogQueries.every(query => !('date' in query))).toBe(true)
  })

  it('A explícita (fora da coorte) renderiza o mesmo que sem experimento', async () => {
    const plain = (await openMenu()).find('main').html()
    const explicitA = (await openMenu('a')).find('main').html()
    expect(explicitA).toBe(plain)
  })

  it('B sem dia escolhido: a pergunta vem antes da lista, com os dias do servidor', async () => {
    const page = await openMenu('b')
    const picker = page.find('[data-menu-day-picker]')
    expect(picker.exists()).toBe(true)
    expect(picker.text()).toContain('Para quando?')
    expect(page.find('[data-menu-results]').exists()).toBe(false)
    const options = page.findAll('[data-menu-day-option]').map(button => button.text())
    expect(options[0]).toContain('Hoje')
    expect(options[1]).toContain('Amanhã')
    expect(page.find('[data-menu-day-other]').text()).toContain('Outro dia')
  })

  it('B: escolher amanhã lê o cardápio do dia, mostra a barra e a frase do dia nos itens', async () => {
    const page = await openMenu('b')
    await page.find('[data-menu-day-option="2026-11-25"]').trigger('click')
    await vi.waitFor(() => expect(page.find('[data-menu-day-bar]').exists()).toBe(true))
    await vi.waitFor(() => expect(catalogQueries.some(query => query.date === '2026-11-25')).toBe(true))
    await flushPromises()

    expect(page.find('[data-menu-day-bar]').text()).toContain('Para amanhã, quarta')
    expect(page.find('[data-menu-day-change]').text()).toBe('Trocar')
    const text = page.find('[data-menu-results]').text()
    // Pronto depois da abertura: a hora. Desde a abertura: nada. Esgotado: "Indisponível".
    expect(text).toContain('A partir das 12h')
    expect(text).not.toContain('Lista de espera')
    expect(text).not.toContain('Disponível amanhã')
    expect(text).toContain('Indisponível')

    // Trocar volta à pergunta, com o dia marcado.
    await page.find('[data-menu-day-change]').trigger('click')
    await nextTick()
    expect(page.find('[data-menu-day-picker]').exists()).toBe(true)
    expect(page.find('[data-menu-day-option="2026-11-25"]').attributes('aria-pressed')).toBe('true')
  })

  it('B: a sacola de outro dia abre o cardápio nesse dia, sem perguntar de novo', async () => {
    useState<CartProjection>('storefront-cart').value = {
      ...(useState<CartProjection>('storefront-cart').value || {}),
      is_empty: false,
      items: [],
      day: { date: '2026-11-25', label: 'amanhã, quarta' }
    } as CartProjection
    const page = await openMenu('b')
    await vi.waitFor(() => expect(page.find('[data-menu-day-bar]').exists()).toBe(true))
    expect(page.find('[data-menu-day-picker]').exists()).toBe(false)
    useState<CartProjection>('storefront-cart').value = { ...useState<CartProjection>('storefront-cart').value, is_empty: true, day: null }
  })

  it('B, "Trocar" com a sacola cheia: o item que não dá é nomeado, e "Seguir sem esse item" leva o resto', async () => {
    useState<CartProjection>('storefront-cart').value = {
      ...(useState<CartProjection>('storefront-cart').value || {}),
      is_empty: false,
      items: [],
      day: { date: '2026-11-25', label: 'amanhã, quarta' }
    } as CartProjection
    dayCalls.length = 0
    const page = await openMenu('b')
    await vi.waitFor(() => expect(page.find('[data-menu-day-bar]').exists()).toBe(true))
    await page.find('[data-menu-day-change]').trigger('click')
    await nextTick()
    await page.find('[data-menu-day-option="2026-11-26"]').trigger('click')

    // A casa diz o que não dá, pelo nome, e nada mudou: a barra segue fora, a pergunta fica.
    await vi.waitFor(() => expect(page.find('[data-menu-day-refusal]').exists()).toBe(true))
    expect(page.find('[data-menu-day-refusal]').text()).toContain('Tabatière não está disponível para quinta, 26/11')
    expect(dayCalls[0]).toEqual({ date: '2026-11-26', without: [] })
    // Forma neutra: a casa não sabe o gênero de cada produto.
    expect(page.find('[data-menu-day-refusal]').text()).toContain('sem esse item')
    expect(page.find('[data-menu-day-proceed]').text()).toBe('Seguir sem esse item')

    await page.find('[data-menu-day-proceed]').trigger('click')
    await vi.waitFor(() => expect(page.find('[data-menu-day-bar]').exists()).toBe(true))
    expect(dayCalls[1]).toEqual({ date: '2026-11-26', without: ['TABAT'] })
    expect(page.find('[data-menu-day-bar]').text()).toContain('Para quinta, 26/11')
    useState<CartProjection>('storefront-cart').value = { ...useState<CartProjection>('storefront-cart').value, is_empty: true, day: null }
  })
})

describe('o card manda o dia com o Adicionar (OC-33 B1)', () => {
  const item = DAY_CATALOG.items.find(entry => entry.sku === 'SONHO-CONTRATO') as CatalogItemProjection

  async function mountCard (day?: { date: string, onDay: boolean }) {
    const provide = day
      ? { [MENU_DAY_KEY as symbol]: { date: computed(() => day.date), onDay: computed(() => day.onDay) } }
      : {}
    const card = await mountSuspended(ProductListItem, {
      props: { item },
      global: { provide, stubs: { CartQuantityAction: { props: ['meta'], template: '<button data-stub-add :data-date="meta.date || \'\'" />' } } }
    })
    mounted.push(card)
    return card
  }

  it('fora do cardápio B: o meta é o de sempre, sem data', async () => {
    const card = await mountCard()
    expect(card.find('[data-stub-add]').attributes('data-date')).toBe('')
  })

  it('no cardápio B do dia: a data vai junto, e o selo é a frase do dia', async () => {
    const card = await mountCard({ date: '2026-11-25', onDay: true })
    expect(card.find('[data-stub-add]').attributes('data-date')).toBe('2026-11-25')
    expect(card.find('[data-product-badges]').text()).toBe('A partir das 12h')
  })
})

describe('sacola datada (OC-33 B1)', () => {
  function datedCart (): CartProjection {
    const promise = (ready_at: string) => ({ kind: 'batch', date: '2026-11-26', ready_at, day_label: 'quinta, 26/11', text: '' })
    return {
      items: [
        { line_id: 'l1', sku: 'PAO', name: 'Pão', qty: 1, unit_price_q: 900, total_price_q: 900, price_display: 'R$ 9,00', line_total_display: 'R$ 9,00', line_total_struck_display: null, list_price_q: 900, image_url: null, discount_label: null, promo_price_display: null, is_available: true, availability_warning: null, available_qty: null, is_notifiable: false, is_notify_subscribed: false, is_made_to_order: false, made_to_order_label: '', is_awaiting_confirmation: false, is_ready_for_confirmation: false, confirmation_deadline_iso: null, confirmation_deadline_display: null, planned_for_date: '2026-11-26', planned_for_notice: null, earlier_available_date: null, notes: '', promise: promise('09:00') },
        { line_id: 'l2', sku: 'TAB', name: 'Tabatière', qty: 1, unit_price_q: 900, total_price_q: 900, price_display: 'R$ 9,00', line_total_display: 'R$ 9,00', line_total_struck_display: null, list_price_q: 900, image_url: null, discount_label: null, promo_price_display: null, is_available: true, availability_warning: null, available_qty: null, is_notifiable: false, is_notify_subscribed: false, is_made_to_order: false, made_to_order_label: '', is_awaiting_confirmation: false, is_ready_for_confirmation: false, confirmation_deadline_iso: null, confirmation_deadline_display: null, planned_for_date: '2026-11-26', planned_for_notice: null, earlier_available_date: null, notes: '', promise: promise('11:00') }
      ],
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
      day: { date: '2026-11-26', label: 'quinta, 26/11' },
      actions: [
        { ref: 'checkout', kind: 'navigate', label: 'Finalizar pedido', priority: 'primary', enabled: true, reason: '', method: 'GET', href: '/finalizar' }
      ],
      revision: 1
    } as unknown as CartProjection
  }

  registerEndpoint('/api/v1/storefront/cart/', () => ({ cart: datedCart(), server_now_iso: new Date().toISOString() }))

  async function openCart (variant?: 'a' | 'b') {
    clearNuxtData()
    setShell(variant)
    useState('storefront-cart').value = datedCart()
    useState('storefront-cart-clock-offset').value = 0
    const page = await mountSuspended(CartPage)
    mounted.push(page)
    await flushPromises()
    return page
  }

  beforeEach(() => { document.cookie = 'csrftoken=local-test' })

  it('B: o alto da sacola diz o dia, quando fica tudo pronto e o gesto de trocar', async () => {
    const page = await openCart('b')
    const line = page.find('[data-cart-day-line]')
    expect(line.exists()).toBe(true)
    expect(line.text().replace(/\s*·\s*/g, ' · ').replace(/\s+/g, ' ')).toBe('Para quinta, 26/11 · Tudo pronto a partir das 11h · Trocar')
    expect(page.find('[data-cart-day-change]').attributes('href')).toBe('/menu?trocar=1')
    // Uma frase de "quando" só: a do pedido some sob a do dia.
    expect(page.find('[data-cart-ready-line]').exists()).toBe(false)
  })

  it('A: a sacola de sempre, com a frase do pedido e sem a linha do dia', async () => {
    const page = await openCart('a')
    expect(page.find('[data-cart-day-line]').exists()).toBe(false)
    expect(page.find('[data-cart-ready-line]').text()).toContain('Seu pedido fica pronto quinta, 26/11, a partir das 11h.')
  })
})

describe('checkout no dia da sacola (OC-33 B1, WCAG 3.3.7)', () => {
  const store = new Map<string, string>()
  beforeAll(() => {
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => { store.set(k, String(v)) },
        removeItem: (k: string) => { store.delete(k) },
        clear: () => { store.clear() }
      }
    })
  })
  beforeEach(() => { store.clear() })

  function projection (): CheckoutProjection {
    return {
      copy: {},
      cart: { items: [], is_empty: false, count: 1, subtotal_q: 900, subtotal_display: 'R$ 9,00', actions: [], day: { date: '2026-11-26', label: 'quinta, 26/11' } },
      customer_phone: '+5543999998888',
      customer_name: 'Marina',
      is_authenticated: true,
      requires_authentication: false,
      auth_action: null,
      saved_addresses: [],
      preselected_address_id: null,
      payment_methods: [{ ref: 'cash', label: 'Dinheiro' }],
      default_payment_method: 'cash',
      actions: [],
      fulfillment_options: ['pickup'],
      has_pickup: true,
      has_delivery: false,
      pickup_slots: [],
      earliest_slot_ref: null,
      pickup_grid: 'canonical',
      loyalty_balance_q: 0,
      loyalty_value_display: null,
      max_preorder_days: 30,
      closed_dates_json: '[]',
      is_debug: false,
      support_whatsapp_url: '',
      pickup_hint: '',
      delivery_hint: '',
      card_provider: '',
      default_ddd: '43',
      available_dates: ['2026-11-25', '2026-11-26'],
      closed_weekdays: [6],
      today: '2026-11-24'
    } as unknown as CheckoutProjection
  }

  registerEndpoint('/api/v1/storefront/checkout/', () => ({ checkout: projection() }))
  registerEndpoint('/api/v1/account/passkeys/', () => ({ passkeys: [] }))

  async function openCheckout (variant?: 'a' | 'b') {
    clearNuxtData()
    setShell(variant)
    const page = await mountSuspended(CheckoutPage)
    mounted.push(page)
    await vi.waitFor(() => expect(page.find('[data-checkout-step="when"]').exists()).toBe(true))
    await flushPromises()
    return page
  }

  it('B: abre no dia da sacola, sem perguntar de novo', async () => {
    const page = await openCheckout('b')
    // O passo "Quando" já traz o dia da sacola (quinta, 26/11), e não o primeiro dia livre.
    await vi.waitFor(() => expect(page.find('[data-checkout-step="when"]').text()).toContain('qui, 26/11'))
  })

  it('A: segue a régua de sempre (o primeiro dia disponível)', async () => {
    const page = await openCheckout('a')
    await vi.waitFor(() => expect(page.find('[data-checkout-step="when"]').text()).toContain('Amanhã'))
  })
})
