import { getRequestURL, sendRedirect, type H3Event } from 'h3'

// ENDEREÇO QUE MUDOU MERECE 301, NÃO 404.
//
// A URL do produto é o SKU, e o catálogo trocou de código duas vezes:
// `CROISSANT` → `CT` em agosto, `CT` → `CRO` em 23/09/2026. Quem tinha o
// endereço antigo — o Google, um link no Instagram, o favorito de um cliente —
// passou a receber 404, e a página recomeça do zero na busca.
//
// O mapa vem do Django (`/api/v1/storefront/sku-redirects/`), que o resolve
// contra o catálogo VIVO: só entra código aposentado que chega a produto que
// existe. Ele encadeia (`CROISSANT` → `CT` → `CRO`) e sabe que `FENDU` voltou a
// ser `FENDU` — por isso não é um `dict` copiado para cá, que envelheceria na
// próxima leva de renames.
//
// Guardado em memória por 5 minutos: rename é raro, mas quando acontece a loja
// acompanha no mesmo dia. Mapa que não carrega não derruba a página — sem ele o
// caminho é o 404 de sempre, que é o que já acontecia.

const TTL_MS = 5 * 60 * 1000
const PRODUCT_PREFIX = '/produto/'

let cache: { at: number, redirects: Record<string, string> } | null = null
let inFlight: Promise<Record<string, string>> | null = null

export function resetSkuRedirectCache (): void {
  cache = null
  inFlight = null
}

export function productSkuFromPath (pathname: string): string {
  if (!pathname.startsWith(PRODUCT_PREFIX)) return ''
  const rest = pathname.slice(PRODUCT_PREFIX.length).replace(/\/+$/, '')
  // Só a própria PDP: `/produto/CT/qualquer-coisa` não é rota nossa.
  return rest.includes('/') ? '' : decodeURIComponent(rest)
}

export async function loadSkuRedirects (
  fetchMap: () => Promise<Record<string, string>>,
  now: number = Date.now()
): Promise<Record<string, string>> {
  if (cache && now - cache.at < TTL_MS) return cache.redirects
  if (!inFlight) {
    inFlight = fetchMap()
      .then((redirects) => {
        cache = { at: now, redirects }
        return redirects
      })
      .catch(() => cache?.redirects || {})
      .finally(() => { inFlight = null })
  }
  return inFlight
}

export async function redirectRetiredSku (
  event: H3Event,
  fetchMap: () => Promise<Record<string, string>>
): Promise<boolean> {
  const url = getRequestURL(event)
  const sku = productSkuFromPath(url.pathname)
  if (!sku) return false

  const redirects = await loadSkuRedirects(fetchMap)
  const target = redirects[sku]
  if (!target || target === sku) return false

  // A query segue junto (`?utm_source=`), o destino é o mesmo produto.
  await sendRedirect(event, `${PRODUCT_PREFIX}${encodeURIComponent(target)}${url.search}`, 301)
  return true
}
