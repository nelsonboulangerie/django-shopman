import type { Ref } from 'vue'
import { actionDockFits } from '~/presentation/actionDock'

// Acima disto não há navegação inferior e o cartão não é fixo (`.shop-action-dock` só
// flutua abaixo de `md`, ver tailwind.css): a regra não se aplica.
const DOCK_MEDIA = '(max-width: 767px)'

/**
 * O cartão de ação da base cabe fixo? (#3573, regra em `presentation/actionDock`.)
 *
 * Mede o cartão de verdade (a altura cresce com a fonte do sistema, com a linha de motivo,
 * com o rótulo do botão), o cabeçalho preso no alto e a distância do cartão até a base,
 * e responde `true` enquanto o conteúdo ainda tem a parte dele da tela. Com `false` a
 * página tira o cartão do `position: fixed` (classe `shop-action-dock--in-flow`) e tira a
 * marca `data-focus-obstruction`: no fluxo ele não cobre nada, e o próximo foco, a dica
 * "tem mais abaixo" e o toaster deixam de descontá-lo.
 *
 * Começa em `true`: o servidor e a primeira pintura saem como sempre saíram; a medida só
 * existe no navegador. Escuta o tamanho do cartão e do cabeçalho (a fonte que muda chega
 * por aí) e a janela; tudo cai num quadro de animação, uma medida por quadro.
 */
export function useActionDockFit (target: Ref<HTMLElement | null | undefined>): Ref<boolean> {
  const fits = ref(true)
  if (!import.meta.client) return fits

  let frame = 0
  let sizes: ResizeObserver | null = null

  function measureNow () {
    frame = 0
    const dock = target.value
    if (!dock) return
    if (typeof window.matchMedia === 'function' && !window.matchMedia(DOCK_MEDIA).matches) {
      fits.value = true
      return
    }
    const dockHeight = dock.offsetHeight
    // Escondido (o teclado do checkout aberto, `v-show`): sem medida, mantém o que estava.
    if (dockHeight <= 0) return
    // `bottom` é declarado nos dois modos; no fluxo o navegador devolve o valor calculado.
    const bottomOffset = Number.parseFloat(getComputedStyle(dock).bottom)
    const header = document.querySelector<HTMLElement>('.shop-header-bar')
    fits.value = actionDockFits({
      viewportHeight: window.innerHeight,
      topChrome: header?.offsetHeight ?? 0,
      bottomOffset: Number.isFinite(bottomOffset) ? bottomOffset : 0,
      dockHeight
    })
  }

  function schedule () {
    if (frame) return
    frame = requestAnimationFrame(measureNow)
  }

  function observe () {
    sizes?.disconnect()
    sizes = null
    const dock = target.value
    if (!dock || typeof ResizeObserver !== 'function') return
    sizes = new ResizeObserver(schedule)
    sizes.observe(dock)
    const header = document.querySelector<HTMLElement>('.shop-header-bar')
    if (header) sizes.observe(header)
  }

  // O cartão entra e sai com o dado (`v-if` da sacola vazia): segue o elemento da vez.
  watch(target, () => {
    observe()
    schedule()
  }, { flush: 'post' })
  onMounted(() => {
    observe()
    schedule()
  })
  useEventListener(window, 'resize', schedule)
  onBeforeUnmount(() => {
    if (frame) cancelAnimationFrame(frame)
    sizes?.disconnect()
  })

  return fits
}
