import type { CatalogResponse } from '~/types/shopman'
import { resolveDjangoBaseUrl } from '../utils/djangoBaseUrl'
import { catalogRoutes, sitemapUrls, sitemapXml } from '../utils/sitemap'

// sitemap.xml domain-aware, alimentado pelo catálogo real (Django). Inclui a
// home, o cardápio, cada coleção estática (/colecao/<ref>), cada PDP
// (/produto/<sku>) e as páginas de conteúdo (/faq, /privacidade, /termos). As
// variantes de filtro (?filtro=/?secao=) NÃO entram: elas canonicalizam para
// /menu (anti-duplicate).
export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const djangoBaseUrl = resolveDjangoBaseUrl(config.djangoBaseUrl)
  const origin = getRequestURL(event).origin

  let menu: CatalogResponse
  try {
    // A gêmea pública do catálogo (sem cookie, cacheável na borda): o sitemap só
    // precisa de `sku` e do `ref` das coleções estáticas, e o corpo do anônimo é o
    // mesmo para todos. O `menu/` montava sacola e personalização para nada, e era
    // a leitura mais lenta da loja.
    menu = await $fetch<CatalogResponse>(`${djangoBaseUrl}/api/v1/storefront/public/catalog/`)
  } catch {
    // Catálogo indisponível: falha gritando. Um sitemap 200 só com as rotas fixas
    // diria ao Google que todos os produtos e coleções sumiram; o 503 com
    // Retry-After faz o crawler voltar depois e guardar o sitemap anterior.
    setHeader(event, 'retry-after', 300)
    throw createError({ statusCode: 503, statusMessage: 'Catalog unavailable' })
  }

  setHeader(event, 'content-type', 'application/xml; charset=utf-8')
  return sitemapXml(sitemapUrls({ origin, ...catalogRoutes(menu?.catalog) }))
})
