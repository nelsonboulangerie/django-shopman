import type { Ref } from 'vue'

const NON_TYPING_INPUT_TYPES = new Set([
  'button',
  'checkbox',
  'color',
  'file',
  'hidden',
  'image',
  'radio',
  'range',
  'reset',
  'submit'
])

/** Um controle que pode abrir teclado/picker e precisa de área útil para edição. */
export function isTextEntryControl (target: EventTarget | null): target is HTMLElement {
  if (typeof HTMLElement === 'undefined' || !(target instanceof HTMLElement)) return false
  if (target instanceof HTMLTextAreaElement) return true
  if (target.isContentEditable) return true
  return target instanceof HTMLInputElement && !NON_TYPING_INPUT_TYPES.has(target.type)
}

function isSmallTouchViewport (): boolean {
  if (!import.meta.client) return false
  const small = typeof window.matchMedia === 'function'
    ? window.matchMedia('(max-width: 767px)').matches
    : window.innerWidth < 768
  const coarse = typeof window.matchMedia === 'function'
    ? window.matchMedia('(pointer: coarse)').matches
    : false
  return small && (coarse || navigator.maxTouchPoints > 0)
}

/**
 * Reserva a visual viewport para o campo em edição.
 *
 * Em Safari/iOS o teclado reduz só a visual viewport; em outros navegadores ele
 * pode reduzir também o layout viewport. Por isso a decisão de recolher chrome
 * não depende apenas da geometria: o foco num editor em tela touch antecipa a
 * animação do teclado, e o VisualViewport confirma/reajusta depois.
 */
export function useMobileFormViewport (root: Ref<HTMLElement | null>) {
  const editorFocused = ref(false)
  const { overlap, viewportHeight, isOpen: viewportOccluded } = useVirtualKeyboard()
  const keyboardActive = computed(() => editorFocused.value || viewportOccluded.value)
  let revealTicket = 0

  function activeEditor (): HTMLElement | null {
    if (!import.meta.client) return null
    const active = document.activeElement
    if (!isTextEntryControl(active) || !root.value?.contains(active)) return null
    return active
  }

  function revealActiveEditor () {
    const active = activeEditor()
    if (!active) return
    const visualViewport = window.visualViewport
    const viewportTop = visualViewport?.offsetTop || 0
    const viewportBottom = viewportTop + (visualViewport?.height || window.innerHeight)
    const rect = active.getBoundingClientRect()
    // 4rem = navbar colapsada; 1rem de respiro em cada borda. O dock e a
    // bottom-nav já estão recolhidos enquanto `keyboardActive`.
    const visibleTop = viewportTop + 80
    const visibleBottom = viewportBottom - 16
    if (rect.top < visibleTop || rect.bottom > visibleBottom) {
      active.scrollIntoView({ block: 'center', behavior: 'auto' })
    }
  }

  function scheduleReveal () {
    if (!import.meta.client) return
    const mine = ++revealTicket
    requestAnimationFrame(() => {
      if (mine === revealTicket) revealActiveEditor()
    })
  }

  function syncFocusedEditor () {
    editorFocused.value = isSmallTouchViewport() && !!activeEditor()
    if (editorFocused.value) scheduleReveal()
  }

  function onFocusIn (event: FocusEvent) {
    editorFocused.value = isSmallTouchViewport() && isTextEntryControl(event.target)
    if (editorFocused.value) scheduleReveal()
  }

  function onFocusOut () {
    if (!import.meta.client) return
    requestAnimationFrame(syncFocusedEditor)
  }

  // `viewportHeight` também muda quando o browser usa resizes-content e o
  // overlap calculado é zero. Em ambos os modelos o campo é reavaliado depois
  // da animação do teclado.
  watch([overlap, viewportHeight], scheduleReveal)
  watch(keyboardActive, active => {
    if (!import.meta.client) return
    document.documentElement.classList.toggle('shop-form-keyboard-open', active)
    if (active) scheduleReveal()
  }, { immediate: true })

  onBeforeUnmount(() => {
    revealTicket++
    if (import.meta.client) document.documentElement.classList.remove('shop-form-keyboard-open')
  })

  return { keyboardActive, editorFocused, onFocusIn, onFocusOut, revealActiveEditor }
}
