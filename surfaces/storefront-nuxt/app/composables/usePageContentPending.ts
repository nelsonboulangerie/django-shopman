import type { WatchSource } from 'vue'

// A página de destino diz ao aviso de navegação que o conteúdo dela ainda está
// chegando. Existe porque páginas como /menu montam ANTES do dado (`lazy`, para
// não segurar a tela anterior): a transição termina em poucos milissegundos, o
// `page:finish` chega antes do limiar de 200 ms do `NavigationFeedback`, e o
// aviso "Abrindo o cardápio…" nunca aparecia, mesmo com o catálogo demorando.
// Com o pendente declarado, o aviso segue a espera de verdade, não a transição.

const PAGE_CONTENT_PENDING_KEY = 'storefront-page-content-pending'
const PAGE_CONTENT_WAIT_COPY_KEY = 'storefront-page-content-wait-copy'

/** Título e frase do aviso de espera. */
export interface PageWaitCopy {
  title: string
  detail: string
}

/** Quantas fontes da página atual ainda esperam o dado (0 = conteúdo pronto). */
export function usePageContentPendingCount () {
  return useState<number>(PAGE_CONTENT_PENDING_KEY, () => 0)
}

/**
 * A frase da fase em que a página está, quando ela tem mais de uma espera (ex.:
 * /menu abre a vitrine e depois confirma preços). `null` = a frase do destino.
 * O aviso de navegação é o único narrador da espera: a página não abre um
 * segundo aviso, ela troca a frase deste.
 */
export function usePageContentWaitCopy () {
  return useState<PageWaitCopy | null>(PAGE_CONTENT_WAIT_COPY_KEY, () => null)
}

/**
 * Marca a página como "conteúdo ainda chegando" enquanto `pending` for verdadeiro.
 * Solta sozinha quando o componente desmonta. Só no cliente: no SSR não há aviso.
 */
export function usePageContentPending (
  pending: WatchSource<boolean | undefined>,
  phaseCopy?: WatchSource<PageWaitCopy | null | undefined>
) {
  if (import.meta.server) return
  const count = usePageContentPendingCount()
  const waitCopy = usePageContentWaitCopy()
  let marked = false

  function mark (value: boolean) {
    if (value === marked) return
    marked = value
    count.value = Math.max(0, count.value + (value ? 1 : -1))
  }

  watch(pending, value => mark(!!value), { immediate: true })
  if (phaseCopy) {
    watch(phaseCopy, (value) => { waitCopy.value = value || null }, { immediate: true })
  }
  onScopeDispose(() => {
    mark(false)
    if (phaseCopy) waitCopy.value = null
  })
}
