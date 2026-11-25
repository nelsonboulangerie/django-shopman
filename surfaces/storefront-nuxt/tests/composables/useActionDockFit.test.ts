import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import { useActionDockFit } from '~/composables/useActionDockFit'

// #3573 (X11): com a fonte do sistema a 200 % o cartão do total da sacola tomava, com a
// navegação, 426 de 812 px, e o que a página levava ao meio da tela ficava atrás dele.
// O cartão mede a si mesmo e desce para o fluxo quando não cabe; no fluxo ele deixa de
// ser obstáculo (`data-focus-obstruction`), para o próximo foco e a dica de rolagem.

const nextFrame = () => new Promise(resolve => requestAnimationFrame(() => resolve(null)))

let dockHeight = 98
let phone = true

beforeEach(() => {
  dockHeight = 98
  phone = true
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 812 })
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query === '(max-width: 767px)' ? phone : false,
    media: query,
    addEventListener () {},
    removeEventListener () {}
  }))
  const header = document.createElement('header')
  header.className = 'shop-header-bar'
  Object.defineProperty(header, 'offsetHeight', { configurable: true, get: () => (dockHeight > 200 ? 134 : 70) })
  document.body.appendChild(header)
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

/** A sacola em miniatura: o mesmo cartão, com a mesma ligação de classe e de marca. */
async function mountDock () {
  const Dock = defineComponent({
    setup () {
      const el = ref<HTMLElement | null>(null)
      const floats = useActionDockFit(el)
      return () => h('div', {
        ref: el,
        class: ['shop-action-dock', { 'shop-action-dock--in-flow': !floats.value }],
        style: { bottom: dockHeight > 200 ? '160px' : '80px' },
        'data-focus-obstruction': floats.value ? '' : undefined,
        onVnodeMounted: ({ el: node }: { el: HTMLElement }) => {
          Object.defineProperty(node, 'offsetHeight', { configurable: true, get: () => dockHeight })
        }
      }, 'Total do pedido')
    }
  })
  const wrapper = await mountSuspended(Dock, { attachTo: document.body })
  await nextFrame()
  await nextFrame()
  return wrapper
}

describe('useActionDockFit', () => {
  it('fonte normal: o cartão segue fixo e marcado como obstáculo', async () => {
    const wrapper = await mountDock()
    const dock = wrapper.find('.shop-action-dock')
    expect(dock.classes()).not.toContain('shop-action-dock--in-flow')
    expect(dock.attributes('data-focus-obstruction')).toBe('')
  })

  it('fonte a 200 %: o cartão de 266 px desce para o fluxo e deixa de ser obstáculo', async () => {
    dockHeight = 266
    const wrapper = await mountDock()
    const dock = wrapper.find('.shop-action-dock')
    expect(dock.classes()).toContain('shop-action-dock--in-flow')
    expect(dock.attributes('data-focus-obstruction')).toBeUndefined()
  })

  it('a janela que muda refaz a medida: a fonte volta ao normal e o cartão volta a flutuar', async () => {
    dockHeight = 266
    const wrapper = await mountDock()
    expect(wrapper.find('.shop-action-dock').classes()).toContain('shop-action-dock--in-flow')

    dockHeight = 98
    window.dispatchEvent(new Event('resize'))
    await nextFrame()
    await nextFrame()
    expect(wrapper.find('.shop-action-dock').classes()).not.toContain('shop-action-dock--in-flow')
  })

  it('do tablet para cima o cartão não é fixo: a regra não se aplica', async () => {
    phone = false
    dockHeight = 266
    const wrapper = await mountDock()
    expect(wrapper.find('.shop-action-dock').classes()).not.toContain('shop-action-dock--in-flow')
  })
})
