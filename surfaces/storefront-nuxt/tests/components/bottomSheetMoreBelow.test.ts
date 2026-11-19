// A seta "tem mais abaixo" da folha fala de conteúdo, não de respiro. Na revisão do
// checkout (WP-L05) ela aparecia por causa de um ou dois pixels de folga e cobria a
// última linha do card do dinheiro, que já estava inteira na tela.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import BottomSheet from '~/components/BottomSheet.vue'

type Entry = { isIntersecting: boolean }
let deliver: ((entries: Entry[]) => void) | null = null
let observedOptions: IntersectionObserverInit | undefined

beforeEach(() => {
  deliver = null
  observedOptions = undefined
  vi.stubGlobal('IntersectionObserver', class {
    constructor (cb: (entries: Entry[]) => void, options?: IntersectionObserverInit) {
      deliver = cb
      observedOptions = options
    }

    observe () {}
    disconnect () {}
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

async function mountSheet () {
  const Host = defineComponent({
    setup: () => () => h(BottomSheet, { open: true, title: 'Revise seu pedido' }, {
      default: () => h('p', 'Conteúdo da folha')
    })
  })
  const wrapper = await mountSuspended(Host, { attachTo: document.body })
  await nextTick()
  await nextTick()
  return wrapper
}

function chevron () {
  return document.querySelector('.animate-bounce')?.parentElement as HTMLElement | null
}

describe('BottomSheet: "tem mais abaixo"', () => {
  it('a folga do fim do corpo não conta como conteúdo por rolar', async () => {
    await mountSheet()

    // Margem só embaixo, de um passo de espaçamento: o fim "aparece" um pouco antes.
    expect(observedOptions?.rootMargin).toBe('0px 0px 16px 0px')
  })

  it('a seta aparece enquanto falta conteúdo e some quando o fim chega', async () => {
    await mountSheet()
    expect(deliver).toBeTruthy()

    deliver!([{ isIntersecting: false }])
    await nextTick()
    expect(chevron()?.className).toContain('opacity-100')

    deliver!([{ isIntersecting: true }])
    await nextTick()
    expect(chevron()?.className).toContain('opacity-0')
  })
})
