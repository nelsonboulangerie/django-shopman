import { favoriteNotedAlertMessage } from '~/presentation/stockNotify'
import type { FavoriteToggleResponse } from '~/types/shopman'

// Estado otimista de favoritos do cliente (WP-4). Um único mapa SKU→bool
// compartilhado entre todos os corações (card/PDP) e a coleção "Seus favoritos",
// para que favoritar num lugar reflita em todos. A projeção server-side traz o
// `is_favorite` inicial; este overlay registra as mudanças da sessão.
export function useFavoritesState () {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()
  const { isAuthenticated } = useShopSession()
  const { setStockNotifySubscribed } = useStockNotifyTransientState()

  const overrides = useState<Record<string, boolean>>('shopman-favorites', () => ({}))
  // Incrementa APÓS cada mutação confirmada pelo servidor — sinal de reload para
  // coleções derivadas (evita o race do overlay otimista vs. GET).
  const version = useState<number>('shopman-favorites-version', () => 0)

  function isFavorite (sku: string, fallback = false): boolean {
    const override = overrides.value[sku]
    return override === undefined ? fallback : override
  }

  // Alterna otimista; reverte em falha. Retorna o novo estado, ou null se anônimo
  // (a UI convida a logar). Idempotente do lado do servidor.
  async function toggle (sku: string, current: boolean): Promise<boolean | null> {
    if (!isAuthenticated.value) return null

    const next = !current
    overrides.value = { ...overrides.value, [sku]: next }
    try {
      const result = await $fetch<FavoriteToggleResponse | undefined>(apiPath(`/api/v1/account/favorites/${encodeURIComponent(sku)}/`), {
        method: next ? 'POST' : 'DELETE',
        headers: await csrfHeaders(),
        credentials: 'include'
      })
      // Favoritar um esgotado pode anotar o aviso (e desfavoritar nunca o
      // cancela): o sino de todo botão deste SKU segue o que o servidor disse.
      if (typeof result?.is_notify_subscribed === 'boolean') {
        setStockNotifySubscribed(sku, result.is_notify_subscribed)
      }
      if (result?.stock_alert_noted === true && import.meta.client) {
        useSonner.success(favoriteNotedAlertMessage())
      }
      version.value += 1
      return next
    } catch (e) {
      overrides.value = { ...overrides.value, [sku]: current }
      if (import.meta.client) useSonner.error(errorDetail(e, 'Não foi possível salvar o favorito.'))
      throw e
    }
  }

  return { isFavorite, toggle, isAuthenticated, version }
}
