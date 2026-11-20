// #2609 (achado pela J1, WP-L00): dois nomes que o leitor de tela não ouvia.
//   1. Aba "Histórico" do acompanhamento: o título do passo ("Recebido", "Aceito")
//      estava com aria-hidden e sumia da árvore de acessibilidade.
//   2. Cabeçalho no desktop: o link da sacola se chamava "Ver sacola", sem a contagem
//      que o selo mostra; a barra de baixo (celular) já dizia "Sacola, 2 itens".
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import ShopHeader from '~/components/ShopHeader.vue'
import AppBottomNav from '~/components/AppBottomNav.vue'
import { cartLinkName } from '~/presentation/cart'
import UiTimeline from '~/components/Ui/Timeline/Timeline.vue'
import UiTimelineItem from '~/components/Ui/Timeline/Item.vue'
import UiTimelineHeader from '~/components/Ui/Timeline/Header.vue'
import UiTimelineSeparator from '~/components/Ui/Timeline/Separator.vue'
import UiTimelineTitle from '~/components/Ui/Timeline/Title.vue'
import UiTimelineIndicator from '~/components/Ui/Timeline/Indicator.vue'

async function setCart (items_count: number) {
  const { useCartState } = await import('~/composables/useCartState')
  const store = useCartState()
  store.cart.value = { ...store.cart.value, items_count, is_empty: items_count === 0 } as never
}

describe('cartLinkName: um nome só para o link da sacola', () => {
  it('diz a contagem que o selo mostra, no singular e no plural', () => {
    expect(cartLinkName({ is_empty: true, items_count: 0 })).toBe('Sacola')
    expect(cartLinkName({ is_empty: false, items_count: 1 })).toBe('Sacola, 1 item')
    expect(cartLinkName({ is_empty: false, items_count: 5 })).toBe('Sacola, 5 itens')
  })
})

describe('link da sacola: cabeçalho e barra de baixo com o mesmo nome', () => {
  it('o cabeçalho diz quantos itens tem, e o selo fica fora do nome', async () => {
    vi.stubGlobal('$fetch', vi.fn().mockResolvedValue({}))
    await setCart(2)
    const header = await mountSuspended(ShopHeader, { route: '/' })
    const link = header.get('[data-header-cart-link]')
    expect(link.attributes('aria-label')).toBe('Sacola, 2 itens')
    const badge = link.findAll('*').find(el => el.text() === '2')
    expect(badge?.element.closest('[aria-hidden="true"]')).not.toBeNull()

    const nav = await mountSuspended(AppBottomNav, { route: '/' })
    const bag = nav.findAll('[data-bottom-nav-link]').find(a => a.attributes('href') === '/sacola')
    expect(bag?.attributes('aria-label')).toBe(link.attributes('aria-label'))
  }, 30_000)

  it('com a sacola vazia, o nome é só "Sacola"', async () => {
    vi.stubGlobal('$fetch', vi.fn().mockResolvedValue({}))
    await setCart(0)
    const header = await mountSuspended(ShopHeader, { route: '/' })
    expect(header.get('[data-header-cart-link]').attributes('aria-label')).toBe('Sacola')
  }, 30_000)
})

describe('Histórico: o nome do passo chega ao leitor de tela', () => {
  it('o título do passo não é aria-hidden; o indicador e o separador seguem decorativos', async () => {
    const Harness = defineComponent({
      setup: () => () => h(UiTimeline, { modelValue: 1 }, () => [
        h(UiTimelineItem, { step: 1 }, () => [
          h(UiTimelineHeader, null, () => [
            h(UiTimelineSeparator),
            h(UiTimelineTitle, null, () => 'Aceito'),
            h(UiTimelineIndicator)
          ])
        ])
      ])
    })
    const wrapper = await mountSuspended(Harness)
    const title = wrapper.get('[data-slot="timeline-title"]')
    expect(title.text()).toBe('Aceito')
    expect(title.attributes('aria-hidden')).toBeUndefined()
    expect(title.element.closest('[aria-hidden="true"]')).toBeNull()
    expect(wrapper.get('[data-slot="timeline-indicator"]').attributes('aria-hidden')).toBe('true')
  }, 30_000)
})
