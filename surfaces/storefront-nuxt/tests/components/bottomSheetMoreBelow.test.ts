// A seta "tem mais abaixo" da folha fala de conteúdo, não de respiro. Na revisão do
// checkout (WP-L05) ela aparecia por causa de um ou dois pixels de folga e cobria a
// última linha do card do dinheiro, que já estava inteira na tela.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import BottomSheet from '~/components/BottomSheet.vue'

type Entry = { boundingClientRect: { top: number }, rootBounds: { bottom: number } | null }
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

async function mountSheet (surface: 'card' | 'muted' = 'card') {
  const Host = defineComponent({
    setup: () => () => h(BottomSheet, { open: true, title: 'Revise seu pedido', surface }, {
      default: () => h('p', 'Conteúdo da folha')
    })
  })
  const wrapper = await mountSuspended(Host, { attachTo: document.body })
  await nextTick()
  await nextTick()
  return wrapper
}

function hint () {
  return document.querySelector('[data-more-below-contained] [data-more-below]') as HTMLElement | null
}

// O fim do conteúdo (o sentinela) contra a linha de baixo da caixa observada.
const still = { boundingClientRect: { top: 900 }, rootBounds: { bottom: 600 } }
const reached = { boundingClientRect: { top: 590 }, rootBounds: { bottom: 600 } }

// #2414: a folha usa o mesmo <MoreBelow /> da página, no modo caixa, em vez da
// dica antiga desenhada à mão.
describe('BottomSheet: "tem mais abaixo"', () => {
  it('a folga do fim do corpo não conta como conteúdo por rolar', async () => {
    await mountSheet()

    // Margem só embaixo, de um passo de espaçamento: o fim "aparece" um pouco antes.
    expect(observedOptions?.rootMargin).toBe('0px 0px 16px 0px')
    expect(observedOptions?.root).toBeInstanceOf(HTMLElement)
  })

  it('a dica aparece enquanto falta conteúdo e some quando o fim chega', async () => {
    await mountSheet()
    expect(deliver).toBeTruthy()

    deliver!([still])
    await nextTick()
    expect(hint()).not.toBeNull()
    expect(hint()!.querySelector('[data-more-below-jump]')?.getAttribute('aria-label')).toBe('Ir para o fim do conteúdo')

    deliver!([reached])
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 250))
    expect(hint()).toBeNull()
  })

  it('a dica mora na folha (sem teleporte) e desbota para a cor dela', async () => {
    await mountSheet('muted')
    deliver!([still])
    await nextTick()
    expect(document.querySelector('body > [data-more-below]')).toBeNull()
    expect(hint()!.querySelector('.bg-gradient-to-t')?.className).toContain('from-muted')
  })
})
