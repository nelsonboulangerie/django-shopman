import type { CatalogResponse } from '~/types/shopman'
import { resolveDjangoBaseUrl } from '../utils/djangoBaseUrl'
import { sitemapUrls, sitemapXml } from '../utils/sitemap'

// sitemap.xml domain-aware, alimentado pelo catálogo real (Django). Inclui a
// home, o cardápio, cada coleção estática (/colecao/<ref>), cada PDP
// (/produto/<sku>) e as páginas de conteúdo (/faq, /privacidade, /termos). As
// variantes de filtro (?filtro=/?secao=) NÃO entram — elas canonicalizam para
// /menu (anti-duplicate).
export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const djangoBaseUrl = resolveDjangoBaseUrl(config.djangoBaseUrl)
  const origin = getRequestURL(event).origin

  let skus: string[] = []
  let collectionRefs: string[] = []
  try {
    // A gêmea pública do catálogo (sem cookie, cacheável na borda): o sitemap só
    // precisa de `sku` e do `ref` das coleções estáticas, e o corpo do anônimo é o
    // mesmo para todos. O `menu/` montava sacola e personalização para nada, e era
    // a leitura mais lenta da loja.
    const menu = await $fetch<CatalogResponse>(`${djangoBaseUrl}/api/v1/storefront/public/catalog/`)
    const items = menu?.catalog?.items || []
    skus = [...new Set(items.map(item => item.sku).filter(Boolean))]
    // Só coleções ESTÁTICAS viram rota indexável; seções dinâmicas ("Destaques"
    // etc.) são curadoria volátil → ficam fora do sitemap.
    const sections = menu?.catalog?.sections || []
    collectionRefs = [...new Set(sections.filter(s => s && !s.is_dynamic && s.ref).map(s => s.ref))]
  } catch {
    // Catálogo indisponível: ainda servimos as rotas estáticas.
  }

  setHeader(event, 'content-type', 'application/xml; charset=utf-8')
  return sitemapXml(sitemapUrls({ origin, collectionRefs, skus }))
})
