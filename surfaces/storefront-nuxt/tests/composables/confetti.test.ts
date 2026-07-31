import { afterEach, describe, expect, it, vi } from 'vitest'
import { dispararConfetti, prefereMenosMovimento } from '~/composables/useConfetti'

// happy-dom não implementa canvas 2d; o teste não valida o desenho, e sim o
// contrato: nada animado sob movimento reduzido, e a camada decorativa fora da
// árvore de acessibilidade quando anima.
function comCanvasFalso () {
  const ctx = new Proxy({}, { get: () => () => {} })
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as never)
}

function comMatchMedia (reduzido: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduzido && query.includes('prefers-reduced-motion'),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {}
  }))
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  document.querySelectorAll('canvas').forEach(c => c.remove())
})

describe('confete do momento yoin', () => {
  it('não anima para quem pediu menos movimento', () => {
    comMatchMedia(true)

    expect(prefereMenosMovimento()).toBe(true)
    expect(dispararConfetti()).toBe(false)
    // E, o que importa de verdade: nada é inserido na página.
    expect(document.querySelectorAll('canvas')).toHaveLength(0)
  })

  it('anima quando o movimento é bem-vindo', () => {
    comMatchMedia(false)
    comCanvasFalso()

    expect(dispararConfetti(10)).toBe(true)

    const canvas = document.querySelector('canvas')
    expect(canvas).not.toBeNull()
    // Decoração pura: fora da árvore de acessibilidade e sem capturar clique,
    // senão o confete viraria uma camada invisível bloqueando a tela.
    expect(canvas!.getAttribute('aria-hidden')).toBe('true')
    expect(canvas!.style.pointerEvents).toBe('none')
  })
})
