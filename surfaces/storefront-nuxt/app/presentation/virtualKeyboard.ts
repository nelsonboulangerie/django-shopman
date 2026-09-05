// Geometria do teclado virtual — a régua que faz um painel `fixed` parar de se
// esconder embaixo do teclado.
//
// Um elemento `position: fixed` se ancora ao *layout viewport*. O teclado do iOS
// (e o do Android no modo padrão `interactive-widget: resizes-visual`) NÃO encolhe
// o layout viewport: ele encolhe só o *visual viewport*, a janelinha que o usuário
// realmente enxerga. Resultado medido no alpha: o bottom-sheet do "Avise-me" ficava
// colado na base do layout viewport, ou seja, POR BAIXO do teclado, e a pessoa
// digitava às cegas. `max-h-[85dvh]` não socorre, porque `dvh` mede o mesmo layout
// viewport.
//
// A régua honesta é `window.visualViewport`. O quanto da base do layout viewport
// está escondido é `innerHeight - (height + offsetTop)`: `height` é o que sobrou
// visível e `offsetTop` é o quanto o browser empurrou a janela para cima sozinho
// ao focar o campo. Essa conta vale nos dois mundos — onde o teclado encolhe o
// layout viewport ela dá zero, e a folga do CSS já basta.

export interface ViewportGeometry {
  /** Altura do layout viewport (`window.innerHeight`). */
  innerHeight: number
  /** Altura do visual viewport (`visualViewport.height`). */
  viewportHeight: number
  /** Deslocamento do visual viewport dentro do layout (`visualViewport.offsetTop`). */
  offsetTop: number
  /** Zoom do visual viewport (`visualViewport.scale`); pinch não é teclado. */
  scale?: number
}

// Piso de ruído. As barras retráteis do Safari/Chrome mobile já fazem o visual
// viewport divergir do layout em algumas dezenas de pixels sem teclado nenhum;
// um teclado de verdade num iPhone X passa de 290px. Compensar abaixo disso só
// faria o painel tremer ao rolar a página.
export const KEYBOARD_MIN_OVERLAP = 120

/** Respiro entre o topo do teclado e a base do painel. */
export const SHEET_KEYBOARD_GAP = 8

/** Altura mínima do painel — abaixo disso não cabe nem um campo com rótulo. */
export const SHEET_MIN_HEIGHT = 168

/**
 * Quantos pixels da base do layout viewport estão cobertos pelo teclado.
 * Zero quando não há teclado (ou quando o que mudou foi zoom, não teclado).
 */
export function keyboardOverlap (geometry: ViewportGeometry): number {
  const { innerHeight, viewportHeight, offsetTop } = geometry
  const scale = geometry.scale ?? 1
  if (!(innerHeight > 0) || !(viewportHeight > 0)) return 0
  // Pinch-zoom também encolhe o visual viewport, e empurrar o painel aí seria
  // mover a tela debaixo do dedo de quem só quis dar zoom.
  if (scale > 1.01) return 0
  const hidden = innerHeight - (viewportHeight + (offsetTop || 0))
  if (!Number.isFinite(hidden) || hidden < KEYBOARD_MIN_OVERLAP) return 0
  // Teto de sanidade: nenhum teclado come a tela inteira, e um valor absurdo
  // (medida a meio caminho da animação) jogaria o painel para fora.
  return Math.min(Math.round(hidden), Math.round(innerHeight * 0.9))
}

export interface SheetPanelStyle {
  bottom: string
  maxHeight?: string
}

/**
 * Estilo inline do painel do bottom-sheet.
 *
 * Sem teclado, a única correção é somar a barra de gestos (iPhone X e afins) à
 * folga de 1rem que a classe já dá. Com teclado, o painel sobe para o topo dele
 * e a altura máxima passa a ser o que sobrou de visual viewport — senão o painel
 * caberia na conta do layout viewport e voltaria a vazar para baixo.
 */
export function sheetPanelStyle (overlap: number, viewportHeight: number): SheetPanelStyle {
  if (!(overlap > 0)) {
    return { bottom: 'calc(1rem + env(safe-area-inset-bottom, 0px))' }
  }
  const available = Math.max(
    Math.round(viewportHeight) - SHEET_KEYBOARD_GAP * 2,
    SHEET_MIN_HEIGHT
  )
  return {
    bottom: `${Math.round(overlap) + SHEET_KEYBOARD_GAP}px`,
    maxHeight: `${available}px`
  }
}
