import { retainedRemoteMutationKey, forgetRemoteMutationKey } from '~/utils/remoteMutations'
import type { CartProjection, ReorderConflictProjection, Action } from '~/types/shopman'

export function useReorder () {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()
  const { setFromServer } = useCartState()
  const pending = useState<Record<string, boolean>>('storefront-reorder-pending', () => ({}))
  const conflict = useState<ReorderConflictProjection | null>('storefront-reorder-conflict', () => null)

  const outcome = useState<{ added: Array<{ sku: string, name: string }>, skipped: string[], ok: boolean } | null>('storefront-reorder-outcome', () => null)
  const keys = useState<Record<string, string>>('storefront-reorder-keys', () => ({}))

  async function submit (orderRef: string, mode: 'append' | 'replace' = 'append') {
    if (pending.value[orderRef]) return null
    const intent = `${orderRef}:${mode}`
    keys.value[intent] ||= retainedRemoteMutationKey(`reorder:${intent}`, `reorder-${mode}`)
    pending.value = { ...pending.value, [orderRef]: true }
    try {
      const response = await $fetch<{ ok?: boolean, cart?: CartProjection, added?: Array<{ sku: string, name: string }>, skipped?: string[], replayed?: boolean }>(apiPath(`/api/v1/orders/${encodeURIComponent(orderRef)}/reorder/`), {
        method: 'POST',
        headers: {
          ...(await csrfHeaders()),
          'Idempotency-Key': keys.value[intent]
        },
        credentials: 'include',
        body: { mode }
      })
      if (response.cart) setFromServer(response.cart)
      outcome.value = { added: response.added || [], skipped: response.skipped || [], ok: response.ok === true }
      forgetRemoteMutationKey(`reorder:${intent}`)
      keys.value = omitKey(keys.value, intent)
      if (import.meta.client && response.ok && !outcome.value.skipped.length) useSonner.success(response.replayed ? 'Esta tentativa já foi processada. Sua sacola está atualizada.' : 'Itens adicionados ao carrinho.')
      if (import.meta.client) await navigateTo('/sacola')
      conflict.value = null
      return response
    } catch (e) {
      const { status, data } = httpError(e)
      if (status === 409 && data) {
        conflict.value = data as unknown as ReorderConflictProjection
      } else if (import.meta.client) {
        useSonner.error(errorDetail(e, 'Não foi possível refazer este pedido.'))
      }
      throw e
    } finally {
      pending.value = omitKey(pending.value, orderRef)
    }
  }

  function orderRefFromAction (action: Action): string {
    const match = action.href.match(/\/orders\/([^/]+)\/reorder\/?/)
    return match?.[1] || ''
  }

  async function performAction (action: Action, mode: 'append' | 'replace' = 'append') {
    const orderRef = orderRefFromAction(action)
    if (!orderRef) return null
    return submit(orderRef, mode)
  }

  return {
    pending,
    outcome,
    conflict,
    submit,
    performAction
  }
}
