import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import MoreBelow from '~/components/MoreBelow.vue'

// A dica no DOM: aparece enquanto o fim do conteúdo não apareceu, some quando
// ele aparece, e flutua acima do que ocupa a base da tela.
//
// O IntersectionObserver é a fronteira com o browser — controlado à mão, para
// o teste dirigir "cheguei ao fim" em vez de torcer pelo layout do happy-dom.

type Entrada = { isIntersecting: boolean, boundingClientRect: { top: number }, rootBounds: { bottom: number } | null }
let entregar: ((entries: Entrada[]) => void) | null = null
let margemObservada = ''

beforeEach(() => {
  entregar = null
  margemObservada = ''
  vi.stubGlobal('IntersectionObserver', class {
    rootMargin: string
    constructor (cb: (entries: Entrada[]) => void, options?: IntersectionObserverInit) {
      entregar = cb
      this.rootMargin = options?.rootMargin || ''
      margemObservada = this.rootMargin
    }
    observe () {}
    disconnect () {}
  })
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {}
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

async function montar (alturaDoObstaculo = 0) {
  if (alturaDoObstaculo > 0) {
    const card = document.createElement('div')
    card.setAttribute('data-focus-obstruction', '')
    document.body.appendChild(card)
    vi.spyOn(card, 'getBoundingClientRect').mockReturnValue({
      top: window.innerHeight - alturaDoObstaculo, bottom: window.innerHeight,
      height: alturaDoObstaculo, left: 0, right: 0, width: 0, x: 0, y: 0, toJSON: () => ({})
    })
  }
  const Pagina = defineComponent({ setup: () => () => h('main', [h(MoreBelow)]) })
  const wrapper = await mountSuspended(Pagina, { attachTo: document.body })
  await nextTick()
  return wrapper
}

const dica = () => document.querySelector('[data-more-below]') as HTMLElement | null

/** O sentinela está em `topo`; a área observada termina em `tela - recuo`. */
function sentinelaEm (topo: number, recuo = 0) {
  const tela = window.innerHeight
  const limite = tela - recuo
  entregar?.([{
    isIntersecting: topo >= 0 && topo <= limite,
    boundingClientRect: { top: topo },
    rootBounds: { bottom: limite }
  }])
}

describe('MoreBelow — a dica de que ainda há conteúdo', () => {
  it('aparece enquanto o fim do conteúdo não apareceu e some quando ele aparece', async () => {
    const wrapper = await montar()
    expect(document.querySelector('[data-more-below-sentinel]')).not.toBeNull()

    sentinelaEm(window.innerHeight + 85)
    await nextTick()
    expect(dica()).not.toBeNull()

    sentinelaEm(Math.round(window.innerHeight / 2))
    await nextTick()
    expect(dica()).toBeNull()
    wrapper.unmount()
  })

  // ⚠️ `isIntersecting` é falso DOS DOIS LADOS. Com ele, a dica sumia no fim do
  // conteúdo e VOLTAVA assim que a pessoa rolava para dentro do rodapé do site
  // — anunciando "tem mais abaixo" justamente no fim da página. Medido no login
  // em 375x667: sentinela em 752 (dica certa), 37 (some, certo), -11 (voltava).
  it('continua sumida depois que o fim do conteúdo passa por cima', async () => {
    const wrapper = await montar()

    sentinelaEm(window.innerHeight + 85)
    await nextTick()
    expect(dica()).not.toBeNull()

    sentinelaEm(37)
    await nextTick()
    expect(dica()).toBeNull()

    sentinelaEm(-11)
    await nextTick()
    expect(dica()).toBeNull()
    wrapper.unmount()
  })

  it('flutua acima do que ocupa a base da tela', async () => {
    const wrapper = await montar(97)
    sentinelaEm(window.innerHeight + 85)
    await nextTick()
    // 97 do card + a folga da regra pura.
    expect(dica()?.style.bottom).toBe('109px')
    wrapper.unmount()
  })

  // O FIM SÓ CONTA ACIMA DO OBSTÁCULO: o sentinela pode estar dentro da tela e
  // atrás do card. Foi o que aconteceu no checkout — sentinela em 626 numa tela
  // de 667, com o card cobrindo de 490 a 587, e a dica sumia cedo demais.
  it('encolhe a área de observação pelo que flutua na base', async () => {
    const wrapper = await montar(97)
    await nextTick()
    expect(margemObservada).toBe('0px 0px -97px 0px')
    wrapper.unmount()
  })

  // Decorativa: nunca rouba clique nem entra na árvore de acessibilidade.
  it('não captura toque e fica fora do leitor de tela', async () => {
    const wrapper = await montar()
    sentinelaEm(window.innerHeight + 85)
    await nextTick()
    expect(dica()?.getAttribute('aria-hidden')).toBe('true')
    expect(dica()?.className).toContain('pointer-events-none')
    wrapper.unmount()
  })
})
