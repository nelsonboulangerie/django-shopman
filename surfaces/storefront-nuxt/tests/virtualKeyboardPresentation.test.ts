// Geometria do teclado virtual: a conta que tira o bottom-sheet de baixo do teclado.
import { describe, expect, it } from 'vitest'
import {
  KEYBOARD_MIN_OVERLAP,
  SHEET_KEYBOARD_GAP,
  SHEET_MIN_HEIGHT,
  keyboardOverlap,
  sheetPanelStyle
} from '~/presentation/virtualKeyboard'

// iPhone X em retrato: layout viewport de 812-ish; teclado + barra de sugestões
// come ~336px, sobrando ~476 de visual viewport.
const IPHONE_X_HEIGHT = 812
const IPHONE_X_KEYBOARD = 336

describe('keyboardOverlap', () => {
  it('sem teclado não compensa nada', () => {
    expect(keyboardOverlap({
      innerHeight: IPHONE_X_HEIGHT,
      viewportHeight: IPHONE_X_HEIGHT,
      offsetTop: 0,
      scale: 1
    })).toBe(0)
  })

  it('mede o teclado do iPhone X pelo visual viewport', () => {
    expect(keyboardOverlap({
      innerHeight: IPHONE_X_HEIGHT,
      viewportHeight: IPHONE_X_HEIGHT - IPHONE_X_KEYBOARD,
      offsetTop: 0,
      scale: 1
    })).toBe(IPHONE_X_KEYBOARD)
  })

  it('desconta o deslocamento que o browser já fez sozinho (offsetTop do iOS)', () => {
    // O iOS empurra o visual viewport para cima ao focar o campo; a parte
    // escondida da BASE do layout viewport é o que sobra depois desse empurrão.
    expect(keyboardOverlap({
      innerHeight: IPHONE_X_HEIGHT,
      viewportHeight: IPHONE_X_HEIGHT - IPHONE_X_KEYBOARD,
      offsetTop: 60,
      scale: 1
    })).toBe(IPHONE_X_KEYBOARD - 60)
  })

  it('ignora a diferença de barra retrátil (ruído abaixo do piso)', () => {
    expect(keyboardOverlap({
      innerHeight: IPHONE_X_HEIGHT,
      viewportHeight: IPHONE_X_HEIGHT - (KEYBOARD_MIN_OVERLAP - 1),
      offsetTop: 0,
      scale: 1
    })).toBe(0)
  })

  it('ignora pinch-zoom, que encolhe o visual viewport e não é teclado', () => {
    expect(keyboardOverlap({
      innerHeight: IPHONE_X_HEIGHT,
      viewportHeight: 400,
      offsetTop: 0,
      scale: 2
    })).toBe(0)
  })

  it('nunca passa de 90% da tela, mesmo com medida absurda no meio da animação', () => {
    expect(keyboardOverlap({
      innerHeight: IPHONE_X_HEIGHT,
      viewportHeight: 1,
      offsetTop: 0,
      scale: 1
    })).toBe(Math.round(IPHONE_X_HEIGHT * 0.9))
  })

  it('geometria inválida (SSR, medida zerada) não compensa', () => {
    expect(keyboardOverlap({ innerHeight: 0, viewportHeight: 0, offsetTop: 0 })).toBe(0)
  })

  // Quando o browser encolhe o LAYOUT viewport junto (Android com
  // `interactive-widget: resizes-content`), a conta dá zero sozinha — a folga do
  // CSS já basta e não há compensação dupla.
  it('não compensa duas vezes quando o layout viewport já encolheu', () => {
    const shrunk = IPHONE_X_HEIGHT - IPHONE_X_KEYBOARD
    expect(keyboardOverlap({
      innerHeight: shrunk,
      viewportHeight: shrunk,
      offsetTop: 0,
      scale: 1
    })).toBe(0)
  })
})

describe('sheetPanelStyle', () => {
  it('sem teclado, soma a barra de gestos à folga da base', () => {
    expect(sheetPanelStyle(0, IPHONE_X_HEIGHT)).toEqual({
      bottom: 'calc(1rem + env(safe-area-inset-bottom, 0px))'
    })
  })

  it('com teclado, sobe o painel para cima dele e limita a altura ao visível', () => {
    const visible = IPHONE_X_HEIGHT - IPHONE_X_KEYBOARD
    expect(sheetPanelStyle(IPHONE_X_KEYBOARD, visible)).toEqual({
      bottom: `${IPHONE_X_KEYBOARD + SHEET_KEYBOARD_GAP}px`,
      maxHeight: `${visible - SHEET_KEYBOARD_GAP * 2}px`
    })
  })

  it('a altura máxima tem piso: painel espremido ainda mostra o campo', () => {
    expect(sheetPanelStyle(700, 40).maxHeight).toBe(`${SHEET_MIN_HEIGHT}px`)
  })

  // O invariante do defeito: com teclado aberto, a base do painel fica ACIMA do
  // topo do teclado, e a altura máxima cabe no que sobrou de tela.
  it('painel inteiro cabe acima do teclado', () => {
    const visible = IPHONE_X_HEIGHT - IPHONE_X_KEYBOARD
    const style = sheetPanelStyle(IPHONE_X_KEYBOARD, visible)
    const bottom = Number.parseInt(style.bottom, 10)
    const maxHeight = Number.parseInt(style.maxHeight!, 10)
    expect(bottom).toBeGreaterThan(IPHONE_X_KEYBOARD)
    expect(bottom + maxHeight).toBeLessThanOrEqual(IPHONE_X_HEIGHT)
  })
})
