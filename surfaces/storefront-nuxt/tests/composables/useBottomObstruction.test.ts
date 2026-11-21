import { afterEach, describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import { useBottomObstruction } from '~/composables/useBottomObstruction'

// #3046: o toaster da loja sobe acima do que flutua na base. A medida é a mesma do
// próximo foco e do MoreBelow (`data-focus-obstruction`), e acompanha o que ENTRA e SAI
// da tela depois de montada (a folha que abre, a barra de ação da rota nova).

afterEach(() => {
  document.body.innerHTML = ''
})

function floating (top: number, height: number): HTMLElement {
  const el = document.createElement('div')
  el.setAttribute('data-focus-obstruction', '')
  el.getBoundingClientRect = () => ({ top, bottom: top + height, height, left: 0, right: 375, width: 375, x: 0, y: top, toJSON: () => ({}) }) as DOMRect
  document.body.appendChild(el)
  return el
}

const nextFrame = () => new Promise(resolve => requestAnimationFrame(() => resolve(null)))

async function mountProbe () {
  let value: { value: number } | null = null
  const Probe = defineComponent({
    setup () {
      value = useBottomObstruction()
      return () => h('div')
    }
  })
  await mountSuspended(Probe, { attachTo: document.body })
  await nextFrame()
  return value!
}

describe('useBottomObstruction', () => {
  it('mede a barra de baixo já na montagem', async () => {
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 812 })
    floating(748, 64)
    const obstruction = await mountProbe()

    expect(obstruction.value).toBe(64)
  })

  it('acompanha o que entra depois: a folha que abre sobe a medida, e ao fechar ela volta', async () => {
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 812 })
    floating(748, 64)
    const obstruction = await mountProbe()
    expect(obstruction.value).toBe(64)

    const sheet = floating(300, 490)
    await nextFrame()
    await nextFrame()
    expect(obstruction.value).toBe(512)

    sheet.remove()
    await nextFrame()
    await nextFrame()
    expect(obstruction.value).toBe(64)
  })

  it('o que flutua no alto da tela não conta como base', async () => {
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 812 })
    floating(0, 64)
    const obstruction = await mountProbe()

    expect(obstruction.value).toBe(0)
  })
})
