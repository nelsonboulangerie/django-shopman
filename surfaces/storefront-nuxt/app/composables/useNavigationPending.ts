import type { MaybeRefOrGetter } from 'vue'

/**
 * Sinal compartilhado: "a página que acabou de montar ainda espera o próprio dado".
 *
 * As páginas da loja carregam a projeção de forma preguiçosa no cliente
 * (`lazy: true`): a troca de rota termina na hora e o dado chega depois, num
 * esqueleto local. Para o aviso de navegação (`NavigationFeedback`) isso parecia
 * uma navegação instantânea, e o `page:finish` cancelava o aviso antes dos 200 ms.
 * Com este registro, o aviso só termina quando a rota terminou E nenhuma página
 * ainda espera o próprio dado.
 *
 * Só escreve no cliente: no SSR a página é entregue com o dado, e o registro
 * serializado no payload fica vazio.
 */
export const NAVIGATION_PENDING_STATE_KEY = 'navigation-pending'

export function useNavigationPendingRegistry () {
  return useState<Record<string, true>>(NAVIGATION_PENDING_STATE_KEY, () => ({}))
}

let sequence = 0

export function useNavigationPending (source: MaybeRefOrGetter<unknown>) {
  if (!import.meta.client) return

  const registry = useNavigationPendingRegistry()
  const id = `page-${++sequence}`

  function release () {
    if (!(id in registry.value)) return
    const { [id]: _released, ...rest } = registry.value
    registry.value = rest
  }

  const stop = watch(() => !!toValue(source), (isPending) => {
    if (isPending) {
      if (!(id in registry.value)) registry.value = { ...registry.value, [id]: true }
    } else {
      release()
    }
  }, { immediate: true, flush: 'sync' })

  onScopeDispose(() => {
    stop()
    release()
  })
}
