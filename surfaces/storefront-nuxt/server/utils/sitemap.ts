// Montagem pura do sitemap.xml — a rota busca o catálogo, esta função só escreve.
// Separada para ser testável sem Nitro nem Django.

export interface SitemapUrl {
  loc: string
  priority: string
}

// Páginas de conteúdo fixas. /faq responde perguntas que as pessoas fazem ao
// Google ("tem entrega?", "abre domingo?"); privacidade e termos existem por lei
// e ficam no fim da fila.
const STATIC_PAGES: ReadonlyArray<{ path: string, priority: string }> = [
  { path: '/faq', priority: '0.6' },
  { path: '/privacy', priority: '0.2' },
  { path: '/terms', priority: '0.2' }
]

function escapeXml (value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

export function sitemapUrls (params: {
  origin: string
  collectionRefs: string[]
  skus: string[]
}): SitemapUrl[] {
  const origin = params.origin.replace(/\/$/, '')
  return [
    { loc: `${origin}/`, priority: '1.0' },
    { loc: `${origin}/menu`, priority: '0.9' },
    ...params.collectionRefs.map(ref => ({ loc: `${origin}/colecao/${encodeURIComponent(ref)}`, priority: '0.7' })),
    ...params.skus.map(sku => ({ loc: `${origin}/produto/${encodeURIComponent(sku)}`, priority: '0.8' })),
    ...STATIC_PAGES.map(page => ({ loc: `${origin}${page.path}`, priority: page.priority }))
  ]
}

export function sitemapXml (urls: SitemapUrl[]): string {
  return `<?xml version="1.0" encoding="UTF-8"?>\n`
    + `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
    + urls.map(url => `  <url><loc>${escapeXml(url.loc)}</loc><priority>${url.priority}</priority></url>`).join('\n')
    + `\n</urlset>\n`
}
