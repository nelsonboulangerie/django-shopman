// EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
// OC-33 B1, direção E2 (dono, 25/11/2026): quem só olha não é interrompido; o
// primeiro "+" com a casa fechada abre a folha "Quando" com o próximo dia marcado e o
// verbo com o dia; depois, o dia é a etapa feita do checkout no topo; "Editar" reabre a
// folha, e trocar o dia com item que não dá mostra o aviso item a item. A: idêntica ao
// main. Quem decide a versão é o servidor (shell `experience`); disponibilidade,
// promessa, dias e recusas vêm do servidor (X13).
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
// A mesma loja, às 19h: hoje já não tem horário (o servidor diz `today_open: false`).
const CLOSED_CATALOG = { ...TODAY_CATALOG, days: { ...TODAY_CATALOG.days!, today_open: false } } as CatalogProjection
let houseClosed = false
const DAY_CATALOG = withRealDates(catalogDayContractJson as unknown as CatalogProjection)

const catalogQueries: Array<Record<string, unknown>> = []
registerEndpoint('/api/v1/storefront/catalog/', (event) => {
  const query = getQuery(event)
  catalogQueries.push(query)
  return { catalog: query.date ? DAY_CATALOG : (houseClosed ? CLOSED_CATALOG : TODAY_CATALOG) }
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
        title: 'Tabatière não está disponível para amanhã, quarta',
        detail: 'Você pode seguir para amanhã, quarta sem esse item, ou manter o dia que tinha.',
        date: '2026-11-25',
        date_label: 'amanhã, quarta',
        items: [{ ref: 'TABAT', sku: 'TABAT', name: 'Tabatière', requested_qty: 1, available_qty: 0 }]
      }
    }
    return { cart: { ...useState<CartProjection>('storefront-cart').value, day: { date: '2026-11-25', label: 'amanhã, quarta' } } }
  }
})

// O Adicionar do card (PUT cart/skus/<sku>/): guarda o corpo, para conferir o dia que foi junto.
const addCalls: Array<Record<string, unknown>> = []
registerEndpoint('/api/v1/cart/skus/PAO-CONTRATO/', {
  method: 'PUT',
  handler: async (event) => {
    addCalls.push(await readBody(event))
    return { cart: { ...useState<CartProjection>('storefront-cart').value, is_empty: false, day: { date: '2026-11-25', label: 'amanhã, quarta' } }, summary: {} }
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
  // O `?dia=` que um teste anterior deixou na URL não pode escolher o dia do seguinte.
  await useRouter().replace({ path: '/menu', query: {} })
  clearNuxtData()
  setShell(variant)
  useState('shopman-menu-day').value = ''
  catalogQueries.length = 0
  const page = await mountSuspended(MenuPage, { global: { stubs: { MenuFavoritesShelf: true } } })
  mounted.push(page)
  await vi.waitFor(() => expect(page.find('[data-menu-results]').exists()).toBe(true))
  await flushPromises()
  return page
}

afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount()
  useState('shopman-menu-day').value = ''
  houseClosed = false
  setShell()
})

// A folha é teleportada para o body (Reka): procura-se nela, não no componente.
const sheet = () => document.querySelector<HTMLElement>('[data-menu-day-sheet]')
const inSheet = (selector: string) => document.querySelector<HTMLElement>(`[data-menu-day-sheet] ${selector}`)

// Um caso só acaba quando nada da sacola está em voo. O Adicionar é uma fila
// (`useCartState`): a resposta do PUT pousa na sacola depois do clique, e a troca de
// `?dia=` passa pelo middleware `cart-settle`, que espera essa fila e relê a sacola antes
// de a rota mudar. Um caso que termina antes disso deixa a resposta pousar DEPOIS do
// `afterEach`, e o caso seguinte abre com a sacola datada: o dia vaza e a etapa aparece
// onde não devia (o "B, casa aberta" da CI, 25/11/2026).
async function cartAtRest (day?: string) {
  if (day) await vi.waitFor(() => expect(useRouter().currentRoute.value.query.dia).toBe(day))
  const { hasPendingMutations } = useCartState()
  await vi.waitFor(() => expect(hasPendingMutations.value).toBe(false))
  await flushPromises()
}

function setCart (day: string | null) {
  useState<CartProjection>('storefront-cart').value = {
    ...(useState<CartProjection>('storefront-cart').value || {}),
    is_empty: !day,
    items: [],
    day: day ? { date: day, label: '' } : null
  } as CartProjection
}

describe('cardápio: o dia do pedido na direção E2 (OC-33 B1)', () => {
  afterEach(() => setCart(null))

  it('A (padrão, sem experimento): a lista de sempre, sem etapa, sem folha, sem data na leitura', async () => {
    const page = await openMenu()
    expect(page.find('[data-menu-day-step]').exists()).toBe(false)
    expect(sheet()).toBeNull()
    expect(catalogQueries.every(query => !('date' in query))).toBe(true)
  })

  it('A explícita (fora da coorte) renderiza o mesmo que sem experimento', async () => {
    // O ícone do Iconify chega quando chega (o primeiro render pode ter o <svg> vazio):
    // a comparação é da página, não do relógio do ícone.
    const withoutIconBodies = (html: string) => html.replace(/<svg\b[\s\S]*?<\/svg>/g, '<svg/>')
    const plain = withoutIconBodies((await openMenu()).find('main').html())
    const explicitA = withoutIconBodies((await openMenu('a')).find('main').html())
    expect(explicitA).toBe(plain)
  })

  it('B, só olhando: nenhuma pergunta de dia no topo enquanto a sacola não tem dia', async () => {
    houseClosed = true
    const page = await openMenu('b')
    expect(page.find('[data-menu-day-step]').exists()).toBe(false)
    expect(sheet()).toBeNull()
    expect(page.find('[data-menu-results]').exists()).toBe(true)
  })

  it('B, casa fechada: o primeiro "+" abre "Quando" com amanhã marcado, e confirmar põe o item no dia', async () => {
    houseClosed = true
    addCalls.length = 0
    const page = await openMenu('b')
    await page.find('button[aria-label="Adicionar Pão do Contrato"]').trigger('click')
    await vi.waitFor(() => expect(sheet()).not.toBeNull())

    expect(sheet()!.textContent).toContain('Quando')
    expect(sheet()!.textContent).toContain('Hoje já encerramos.')
    const tomorrow = inSheet('[data-menu-day-option="2026-11-25"]')!
    expect(tomorrow.textContent).toContain('Amanhã')
    expect(tomorrow.textContent).toContain('Quarta, 25/11')
    expect(inSheet('#menu-day-2026-11-25')!.getAttribute('data-state')).toBe('checked')
    expect(inSheet('[data-menu-day-other]')!.textContent).toContain('Outra data')
    // Nada entrou ainda: a folha segura o gesto até a cliente confirmar o dia.
    expect(addCalls).toHaveLength(0)
    const confirm = inSheet('[data-menu-day-confirm]')!
    expect(confirm.textContent!.trim()).toBe('Encomendar para amanhã')

    confirm.click()
    await vi.waitFor(() => expect(addCalls).toHaveLength(1))
    expect(addCalls[0]).toEqual({ qty: 1, date: '2026-11-25' })
    await vi.waitFor(() => expect(page.find('[data-menu-day-step]').exists()).toBe(true))
    expect(page.find('[data-menu-day-step]').text()).toContain('Quando')
    expect(page.find('[data-menu-day-step]').text()).toContain('qua, 25/11')
    expect(page.find('[data-menu-day-step]').text()).toContain('Editar')
    await vi.waitFor(() => expect(catalogQueries.some(query => query.date === '2026-11-25')).toBe(true))
    await cartAtRest('2026-11-25')
  })

  it('B, casa aberta: o "+" põe na sacola de hoje, sem perguntar', async () => {
    addCalls.length = 0
    setCart(null)
    const page = await openMenu('b')
    // A sacola desta página é vazia e sem dia (a de outro teste não vale aqui).
    expect(page.find('[data-menu-day-step]').exists()).toBe(false)
    await page.find('button[aria-label="Adicionar Pão do Contrato"]').trigger('click')
    await vi.waitFor(() => expect(addCalls).toHaveLength(1))
    expect(addCalls[0]).toEqual({ qty: 1 })
    expect(sheet()).toBeNull()
    await cartAtRest()
  })

  it('B, "Editar" com a sacola cheia: o item que não dá é nomeado na folha, e "Seguir sem esse item" leva o resto', async () => {
    setCart('2026-11-26')
    dayCalls.length = 0
    const page = await openMenu('b')
    await vi.waitFor(() => expect(page.find('[data-menu-day-step]').exists()).toBe(true))
    expect(page.find('[data-menu-day-step]').text()).toContain('qui, 26/11')

    await page.find('[data-menu-day-step] button').trigger('click')
    await vi.waitFor(() => expect(sheet()).not.toBeNull())
    inSheet('#menu-day-2026-11-25')!.click()
    await nextTick()
    inSheet('[data-menu-day-confirm]')!.click()

    await vi.waitFor(() => expect(inSheet('[data-menu-day-refusal]')).not.toBeNull())
    expect(dayCalls[0]).toEqual({ date: '2026-11-25', without: [] })
    expect(inSheet('[data-menu-day-refusal]')!.textContent).toContain('Tabatière não está disponível para amanhã, quarta')
    expect(inSheet('[data-menu-day-refusal]')!.textContent).toContain('sem esse item')
    expect(inSheet('[data-menu-day-proceed]')!.textContent!.trim()).toBe('Seguir sem esse item')
    expect(inSheet('[data-menu-day-keep]')!.textContent!.trim()).toBe('Manter o dia que tinha')

    inSheet('[data-menu-day-proceed]')!.click()
    await vi.waitFor(() => expect(dayCalls[1]).toEqual({ date: '2026-11-25', without: ['TABAT'] }))
    await vi.waitFor(() => expect(page.find('[data-menu-day-step]').text()).toContain('qua, 25/11'))
    await cartAtRest('2026-11-25')
  })
})

describe('o card manda o dia com o Adicionar (OC-33 B1)', () => {
  const item = DAY_CATALOG.items.find(entry => entry.sku === 'SONHO-CONTRATO') as CatalogItemProjection

  async function mountCard (day?: { date: string, onDay: boolean }) {
    const provide = day
      ? { [MENU_DAY_KEY as symbol]: { date: computed(() => day.date), onDay: computed(() => day.onDay), ask: () => false } }
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

  it('B: o dia uma vez só, como a etapa feita; o pedido diz quando fica pronto; a linha só traz a hora que difere', async () => {
    const page = await openCart('b')
    const step = page.find('[data-cart-day-line]')
    expect(step.exists()).toBe(true)
    expect(step.find('[data-checkout-section-state="done"]').exists()).toBe(true)
    expect(step.text()).toContain('Quando')
    expect(step.text()).toContain('qui, 26/11')
    expect(step.text()).toContain('Editar')
    expect(page.find('[data-cart-ready-line]').text()).toBe('Tudo pronto a partir das 11h')
    // O pão fica disponível antes do pedido inteiro; a Tabatière é a hora do pedido.
    const promises = page.findAll('[data-cart-line-promise]').map(node => node.text())
    expect(promises).toEqual(['Disponível a partir das 9h'])
    expect(page.text()).not.toContain('Para quinta')
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
