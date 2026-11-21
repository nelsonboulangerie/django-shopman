import { measureBottomObstruction } from '~/composables/useNextFocus'
import { FOCUS_OBSTRUCTION_ATTRIBUTE } from '~/presentation/nextFocus'

/**
 * Quanto da base da tela está coberto pelo que flutua lá (#3046): a barra de navegação,
 * o card do total do checkout, a barra de ação do produto e da sacola, a folha aberta.
 * É a MESMA medida do próximo foco e do `MoreBelow` (`data-focus-obstruction`).
 *
 * Feita para quem é global e não sabe em que tela está (o toaster da loja): o que
 * flutua na base muda com a rota, com a folha que abre e fecha, e com o card que cresce
 * quando o rótulo do botão muda. Por isso escuta as três coisas: a árvore (quem entrou e
 * saiu, só a lista de filhos e o atributo, não o estilo), o tamanho de quem está
 * marcado agora, e a janela. Tudo cai num quadro de animação, uma medida por quadro.
 */
export function useBottomObstruction () {
  const obstruction = ref(0)
  if (!import.meta.client) return obstruction

  let frame = 0
  let sizes: ResizeObserver | null = null

  function measureNow () {
    frame = 0
    obstruction.value = measureBottomObstruction()
    // Quem está marcado agora: a medida acompanha o tamanho DELES, não só a janela.
    sizes?.disconnect()
    if (typeof ResizeObserver === 'function') {
      sizes = sizes ?? new ResizeObserver(schedule)
      for (const el of document.querySelectorAll(`[${FOCUS_OBSTRUCTION_ATTRIBUTE}]`)) sizes.observe(el)
    }
  }

  function schedule () {
    if (frame) return
    frame = requestAnimationFrame(measureNow)
  }

  let tree: MutationObserver | null = null
  onMounted(() => {
    measureNow()
    if (typeof MutationObserver === 'function') {
      tree = new MutationObserver(schedule)
      tree.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: [FOCUS_OBSTRUCTION_ATTRIBUTE]
      })
    }
  })
  useEventListener(window, 'resize', schedule)
  onBeforeUnmount(() => {
    if (frame) cancelAnimationFrame(frame)
    tree?.disconnect()
    sizes?.disconnect()
  })

  return obstruction
}
