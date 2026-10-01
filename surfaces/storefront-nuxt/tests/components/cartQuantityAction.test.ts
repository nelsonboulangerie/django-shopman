// CartQuantityAction (WP-S6): dispara a mutação real (via useCartState → $fetch) e
// emite `changed`; com qty>0 entrega o controle de quantidade em vez do botão.
//
// D1 (opção 3): o botão nasce ATIVO no HTML do servidor; o toque que chega antes da
// hidratação é guardado pelo script inline (utils/earlyTap.ts) e executado UMA vez
// quando o componente monta.
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { createSSRApp, nextTick } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import CartQuantityAction from '~/components/CartQuantityAction.vue'
import type { ProductMutationMeta } from '~/types/shopman'
import { EARLY_TAP_QUEUE, EARLY_TAP_SCRIPT } from '~/utils/earlyTap'

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return fn
})

const meta: ProductMutationMeta = {
  sku: 'CROISSANT', name: 'Croissant', price_q: 500, price_display: 'R$ 5,00', image_url: null
}

type EarlyTapWindow = Window & { [EARLY_TAP_QUEUE]?: string[] }
const earlyTaps = () => (window as EarlyTapWindow)[EARLY_TAP_QUEUE]!

// O que o servidor entrega antes do app: um botão marcado, sem ouvinte do Vue.
function serverRenderedButton (key: string) {
  const button = document.createElement('button')
  button.type = 'button'
  button.setAttribute('data-early-tap', key)
  document.body.appendChild(button)
  return button
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe('CartQuantityAction', () => {
  beforeAll(() => {
    // Executa o MESMO texto que vai inline no <head>.
    new Function(EARLY_TAP_SCRIPT)()
  })

  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
    fetchMock.mockReset()
    earlyTaps().length = 0
    document.body.innerHTML = ''
  })

  it('renders an add button with an accessible label when qty is 0', async () => {
    const wrapper = await mountSuspended(CartQuantityAction, {
      props: { meta, qty: 0, addIconOnly: true }
    })
    const btn = wrapper.get('button')
    expect(btn.attributes('aria-label')).toBe('Adicionar Croissant')
  })

  it('adds to the cart and emits changed on click (after hydration)', async () => {
    fetchMock.mockResolvedValue({ cart: { items: [{ sku: 'CROISSANT', qty: 1 }], items_count: 1, is_empty: false } })
    const wrapper = await mountSuspended(CartQuantityAction, {
      props: { meta, qty: 0, addTargetQty: 3 }
    })
    await nextTick() // onMounted → hydrated

    await wrapper.get('button').trigger('click')
    await new Promise(r => setTimeout(r, 0)) // deixa a fila de mutação drenar

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0]?.[0]).toContain('/cart/skus/CROISSANT/')
    expect(fetchMock.mock.calls[0]?.[1]?.body).toEqual({ qty: 3 })
    expect(wrapper.emitted('changed')?.[0]).toEqual([3])
  })

  it('does not fire when disabled', async () => {
    const wrapper = await mountSuspended(CartQuantityAction, {
      props: { meta, qty: 0, disabled: true }
    })
    await nextTick()
    await wrapper.get('button').trigger('click')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('replays a tap made before hydration exactly once, even if tapped twice', async () => {
    fetchMock.mockResolvedValue({ cart: { items: [{ sku: 'CROISSANT', qty: 1 }], items_count: 1, is_empty: false } })
    const early = serverRenderedButton('cart-add:CROISSANT:1')
    early.click()
    early.click()
    expect(earlyTaps()).toEqual(['cart-add:CROISSANT:1'])
    expect(early.getAttribute('data-early-tap-pending')).toBe('true')
    expect(fetchMock).not.toHaveBeenCalled()

    const wrapper = await mountSuspended(CartQuantityAction, { props: { meta, qty: 0 } })
    await flush()

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0]?.[0]).toContain('/cart/skus/CROISSANT/')
    expect(fetchMock.mock.calls[0]?.[1]?.body).toEqual({ qty: 1 })
    expect(wrapper.emitted('changed')?.[0]).toEqual([1])
    expect(earlyTaps()).toEqual([])
    expect(early.hasAttribute('data-early-tap-pending')).toBe(false)

    // O mesmo produto numa segunda vitrine não repete a ação: o toque já foi consumido.
    await mountSuspended(CartQuantityAction, { props: { meta, qty: 0 } })
    await flush()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('does not replay an early tap for an unavailable product', async () => {
    earlyTaps().push('cart-add:CROISSANT:1')
    await mountSuspended(CartQuantityAction, { props: { meta, qty: 0, disabled: true } })
    await flush()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('drops the early-tap mark once mounted, so later clicks go to Vue', async () => {
    const wrapper = await mountSuspended(CartQuantityAction, { props: { meta, qty: 0 } })
    await nextTick()
    expect(wrapper.get('button').attributes('data-early-tap')).toBeUndefined()
  })

  it('shows pending while the add is in flight and ignores a second tap', async () => {
    let resolveFetch: (value: unknown) => void = () => {}
    fetchMock.mockImplementation(() => new Promise((resolve) => { resolveFetch = resolve }))
    const wrapper = await mountSuspended(CartQuantityAction, { props: { meta, qty: 0 } })
    await nextTick()

    await wrapper.get('button').trigger('click')
    await nextTick()
    const button = wrapper.get('button')
    expect(button.attributes('aria-busy')).toBe('true')
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
    expect(fetchMock).toHaveBeenCalledOnce()

    resolveFetch({ cart: { items: [{ sku: 'CROISSANT', qty: 1 }], items_count: 1, is_empty: false } })
    await flush()
  })

  // O HTML do servidor é o que o cliente vê antes do app. Produto disponível nunca
  // pode sair dali `disabled` (cara de "Indisponível", toque morto).
  it('server-renders an available product as an active, early-tap-ready button', async () => {
    const nuxtApp = useNuxtApp()
    async function serverHtml (props: Record<string, unknown>) {
      const app = createSSRApp(CartQuantityAction, props)
      app.config.globalProperties.$nuxt = nuxtApp
      Object.assign(app, { $nuxt: nuxtApp })
      return renderToString(app)
    }

    const available = await serverHtml({ meta, qty: 0 })
    expect(available).toContain('data-early-tap="cart-add:CROISSANT:1"')
    expect(available).not.toMatch(/<button[^>]*\sdisabled(?=[\s>=])/)

    const unavailable = await serverHtml({ meta, qty: 0, disabled: true, addLabel: 'Indisponível' })
    expect(unavailable).toMatch(/<button[^>]*\sdisabled(?=[\s>=])/)
    expect(unavailable).not.toContain('data-early-tap')
  })
})
