import type { WatchSource } from 'vue'

// A página de destino diz ao aviso de navegação que o conteúdo dela ainda está
// chegando. Existe porque páginas como /menu montam ANTES do dado (`lazy`, para
// não segurar a tela anterior): a transição termina em poucos milissegundos, o
// `page:finish` chega antes do limiar de 200 ms do `NavigationFeedback`, e o
// aviso "Abrindo o cardápio…" nunca aparecia, mesmo com o catálogo demorando.
// Com o pendente declarado, o aviso segue a espera de verdade, não a transição.

const PAGE_CONTENT_PENDING_KEY = 'storefront-page-content-pending'

/** Quantas fontes da página atual ainda esperam o dado (0 = conteúdo pronto). */
export function usePageContentPendingCount () {
  return useState<number>(PAGE_CONTENT_PENDING_KEY, () => 0)
}

/**
 * Marca a página como "conteúdo ainda chegando" enquanto `pending` for verdadeiro.
 * Solta sozinha quando o componente desmonta. Só no cliente: no SSR não há aviso.
 */
export function usePageContentPending (pending: WatchSource<boolean | undefined>) {
  if (import.meta.server) return
  const count = usePageContentPendingCount()
  let marked = false

  function mark (value: boolean) {
    if (value === marked) return
    marked = value
    count.value = Math.max(0, count.value + (value ? 1 : -1))
  }

  watch(pending, value => mark(!!value), { immediate: true })
  onScopeDispose(() => mark(false))
}
