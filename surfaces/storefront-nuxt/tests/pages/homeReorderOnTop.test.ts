// EXPERIMENT(home-recompra-no-topo) remove_after 2027-02-22
// OC-33 B2: a recompra no topo da home logada, em um gesto. Quem decide a versão é
// o servidor (shell `experience`); a página só muda a POSIÇÃO e a forma do cartão.
// A: idêntica ao main (cartão grande abaixo do herói). B: o cartão sobe para o
// topo, compacto, uma vez só, e só quando a recompra é possível (X1). O gesto é a
// MESMA ação da projeção nas duas versões (X13): preço e disponibilidade de agora
// saem do endpoint de recompra, e o que saiu do cardápio a sacola diz.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import HomePage from '~/pages/index.vue'
import { STOREFRONT_SHELL_KEY } from '~/composables/useStorefrontShell'
import { STOREFRONT_HOME_KEY } from '~/composables/useStorefrontHome'
import type { Action, HomeResponse, ShellResponse } from '~/types/shopman'

const { fetchMock, performAction } = vi.hoisted(() => ({ fetchMock: vi.fn(), performAction: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('useLiveStorefrontHome', () => () => {})
mockNuxtImport('useReorder', () => () => ({ performAction, pending: ref({}) }))

const REORDER: Action = {
  ref: 'reorder',
  kind: 'mutation',
  label: 'Repetir pedido',
  priority: 'primary',
  href: '/api/v1/orders/WEB-100/reorder/',
  method: 'POST',
  enabled: true
} as unknown as Action

function copy (title = '', message = '') {
  return { title, message }
}

function homeWith ({ reorder }: { reorder: boolean }): HomeResponse {
  return {
    home: {
      omotenashi: { audience: 'returning', customer_name: 'João' },
      shop: { brand_name: 'Nelson Boulangerie', tagline: 'Padaria Artesanal', full_address: '' },
      shop_status: { is_open: true, label: 'Aberto agora' },
      notices: [],
      opening_hours: [],
      hero_copy: { reorder_title_prefix: copy('Quer repetir seu'), reorder_title_suffix: copy('último pedido') },
      sections_copy: null,
      faq: [],
      last_order_ref: reorder ? 'WEB-100' : null,
      last_order_items: reorder ? [{ sku: 'CRO', name: 'Croissant', qty: 2 }, { sku: 'BAG', name: 'Baguete', qty: 1 }] : [],
      actions: reorder ? [REORDER] : [],
      featured_items: [],
      origin_channel: null,
      public_config: { whatsapp_url: '' },
      ordering: { state: 'now', next_date: null, day_label: '' }
    },
    cart: {}
  } as unknown as HomeResponse
}

function setShell (variant?: 'a' | 'b') {
  useNuxtApp().payload.data[STOREFRONT_SHELL_KEY] = {
    shell: { experience: variant ? [{ ref: 'home-recompra-no-topo', variant }] : [] },
    cart: {}
  } as unknown as ShellResponse
}

const mounted: Array<{ unmount: () => void }> = []

async function mountHome ({ variant, reorder = true }: { variant?: 'a' | 'b', reorder?: boolean }) {
  setShell(variant)
  useNuxtApp().payload.data[STOREFRONT_HOME_KEY] = homeWith({ reorder })
  const page = await mountSuspended(HomePage, { global: { stubs: { HomeHeroThing: { template: '<div data-home-hero-stub />' } } } })
  mounted.push(page)
  await flushPromises()
  return page
}

function reorderButtons (page: Awaited<ReturnType<typeof mountHome>>) {
  return page.findAll('button').filter(button => button.text().trim() === 'Repetir pedido')
}

describe('home logada: a recompra no topo (OC-33 B2)', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    // Sem pedido em andamento: o banner do pedido ativo não entra na conta.
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/account/orders/active/')) return Promise.resolve({ count: 0 })
      if (url.includes('/storefront/site/')) return Promise.resolve({ site: null })
      return Promise.reject(new Error(`inesperado: ${url}`))
    })
    performAction.mockReset()
    performAction.mockResolvedValue(null)
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
  })

  it('A (padrão, sem experimento): o cartão grande abaixo do herói, como no main', async () => {
    const page = await mountHome({})
    expect(page.find('[data-home-reorder-top]').exists()).toBe(false)
    const card = page.find('[data-home-reorder-card]')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('Quer repetir seu último pedido, João?')
    expect(card.text()).toContain('Croissant')
    // Depois do herói, como no main.
    const html = page.html()
    expect(html.indexOf('data-home-hero-stub')).toBeLessThan(html.indexOf('data-home-reorder-card'))
    expect(reorderButtons(page)).toHaveLength(1)
  })

  it('A explícita (fora da coorte) renderiza o mesmo que sem experimento', async () => {
    const semExperimento = (await mountHome({})).find('main').html()
    const versaoA = (await mountHome({ variant: 'a' })).find('main').html()
    expect(versaoA).toBe(semExperimento)
  })

  it('B: a recompra sobe para o topo, antes do herói, uma vez só e em um gesto', async () => {
    const page = await mountHome({ variant: 'b' })
    const top = page.find('[data-home-reorder-top]')
    expect(top.exists()).toBe(true)
    expect(page.find('[data-home-reorder-card]').exists()).toBe(false)
    const html = page.html()
    expect(html.indexOf('data-home-reorder-top')).toBeLessThan(html.indexOf('data-home-hero-stub'))
    expect(top.text()).toContain('Quer repetir seu último pedido, João?')
    expect(top.text()).toContain('2×')
    expect(top.text()).toContain('Croissant')
    expect(top.text()).toContain('Baguete')
    // Um gesto, uma vez na página inteira.
    const buttons = reorderButtons(page)
    expect(buttons).toHaveLength(1)
    expect(page.text().match(/Quer repetir seu último pedido/g)).toHaveLength(1)
  })

  it('X13: o gesto de B dispara a MESMA ação da projeção que o de A', async () => {
    const a = await mountHome({ variant: 'a' })
    await reorderButtons(a)[0]!.trigger('click')
    const b = await mountHome({ variant: 'b' })
    await reorderButtons(b)[0]!.trigger('click')
    expect(performAction).toHaveBeenCalledTimes(2)
    expect(performAction.mock.calls[0]![0]).toEqual(REORDER)
    expect(performAction.mock.calls[1]![0]).toEqual(REORDER)
  })

  it('X1: B sem recompra possível não oferece o gesto no topo', async () => {
    const page = await mountHome({ variant: 'b', reorder: false })
    expect(page.find('[data-home-reorder-top]').exists()).toBe(false)
    expect(reorderButtons(page)).toHaveLength(0)
  })
})
