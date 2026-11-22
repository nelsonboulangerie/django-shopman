// O aviso de página fica abaixo de TODAS as barras do topo (#3267, regra do dono): com a
// faixa do breadcrumb na página, logo depois dela; sem faixa, primeiro filho de
// `#main-content`. Um aviso só no DOM.
import { beforeEach, describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import PageNotice from '~/components/PageNotice.vue'
import UiBreadcrumbs from '~/components/Ui/Breadcrumbs.vue'
import { usePageNotice, usePageNoticeAnchor } from '~/composables/usePageNotice'

function shell (withBreadcrumb: boolean) {
  // O mesmo desenho do `app.vue` e de uma página com a faixa dourada.
  return defineComponent({
    setup () {
      return () => h('div', { id: 'main-content' }, [
        h(PageNotice),
        h('main', [
          withBreadcrumb
            ? h('div', { class: 'shop-breadcrumb-bar mb-4', 'data-band': '' }, [
                h('div', { class: 'shop-container py-2' }, [
                  h(UiBreadcrumbs, { items: [{ label: 'Início', link: '/' }, { label: 'Finalizar pedido' }] })
                ])
              ])
            : null,
          h('h1', 'Finalize seu pedido')
        ])
      ])
    }
  })
}

describe('onde o aviso de página mora', () => {
  beforeEach(() => {
    usePageNotice().dismiss()
    usePageNoticeAnchor().claims.value = 0
  })

  it('com a faixa do breadcrumb, logo depois dela, e uma vez só', async () => {
    usePageNotice().show('Sua sacola ficou vazia antes do envio.', useRoute().path, {
      tone: 'attention',
      action: { label: 'Ver o cardápio', to: '/menu' }
    })
    const wrapper = await mountSuspended(shell(true))
    await nextTick()

    const notices = wrapper.element.querySelectorAll('[data-page-notice]')
    expect(notices).toHaveLength(1)
    const band = wrapper.element.querySelector('[data-band]')!
    const next = band.nextElementSibling!
    expect(next.hasAttribute('data-page-notice-anchor')).toBe(true)
    expect(next.querySelector('[data-page-notice]')).toBe(notices[0])
    expect(notices[0]!.getAttribute('data-page-notice-placement')).toBe('band')
    // O do shell cedeu o lugar: nada antes da faixa.
    expect(wrapper.element.querySelector('#main-content > [data-page-notice]')).toBeNull()
  })

  it('sem faixa, é o primeiro filho de #main-content (o aviso do #3247 em "/")', async () => {
    usePageNotice().show('Pronto, sua conta foi excluída.', useRoute().path)
    const wrapper = await mountSuspended(shell(false))
    await nextTick()

    const main = wrapper.element.matches('#main-content') ? wrapper.element : wrapper.element.querySelector('#main-content')!
    expect(main.querySelectorAll('[data-page-notice]')).toHaveLength(1)
    expect(main.firstElementChild!.hasAttribute('data-page-notice')).toBe(true)
    expect(main.firstElementChild!.getAttribute('data-page-notice-placement')).toBe('shell')
  })

  it('a faixa devolve o lugar ao sair', async () => {
    usePageNotice().show('Este pedido já foi enviado.', useRoute().path)
    const wrapper = await mountSuspended(shell(true))
    await nextTick()
    expect(usePageNoticeAnchor().claims.value).toBe(1)
    wrapper.unmount()
    expect(usePageNoticeAnchor().claims.value).toBe(0)
  })
})
