import type { MaybeRefOrGetter } from 'vue'
import { keyboardOverlap, sheetPanelStyle } from '~/presentation/virtualKeyboard'

/**
 * Acompanha o teclado virtual pelo `visualViewport` e devolve o estilo do painel
 * do bottom-sheet já posicionado acima dele. A conta mora em
 * `~/presentation/virtualKeyboard` (pura, testada); aqui só há a escuta.
 *
 * `active` liga e desliga a escuta: os listeners só existem enquanto a overlay
 * está aberta, então um sheet fechado não custa nada.
 */
export function useVirtualKeyboard (active: MaybeRefOrGetter<boolean> = true) {
  const overlap = ref(0)
  const viewportHeight = ref(0)

  const viewport = computed(() =>
    import.meta.client && toValue(active) ? window.visualViewport ?? null : null
  )

  function measure () {
    if (!import.meta.client) return
    const vv = window.visualViewport
    if (!vv || !toValue(active)) {
      overlap.value = 0
      return
    }
    viewportHeight.value = vv.height
    overlap.value = keyboardOverlap({
      innerHeight: window.innerHeight,
      viewportHeight: vv.height,
      offsetTop: vv.offsetTop,
      scale: vv.scale
    })
  }

  // `scroll` importa tanto quanto `resize`: no iOS o browser desloca o visual
  // viewport (offsetTop) ao focar o campo, sem redimensionar de novo.
  useEventListener(viewport, 'resize', measure)
  useEventListener(viewport, 'scroll', measure)
  useEventListener(() => (import.meta.client ? window : null), 'orientationchange', () =>
    requestAnimationFrame(measure)
  )

  watch(() => toValue(active), open => {
    if (open) nextTick(measure)
    else overlap.value = 0
  }, { immediate: true })

  onMounted(measure)

  const isOpen = computed(() => overlap.value > 0)
  const panelStyle = computed(() => sheetPanelStyle(overlap.value, viewportHeight.value))

  return { overlap, viewportHeight, isOpen, panelStyle, measure }
}
