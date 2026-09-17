import { describe, expect, it } from 'vitest'
import { sitemapUrls, sitemapXml } from '../server/utils/sitemap'

describe('sitemap', () => {
  it('usa o origin da request e inclui catálogo e páginas de conteúdo', () => {
    const urls = sitemapUrls({ origin: 'https://menu.loja.test/', collectionRefs: ['rusticos'], skus: ['PH', 'CROIS 01'] })
    expect(urls).toEqual([
      { loc: 'https://menu.loja.test/', priority: '1.0' },
      { loc: 'https://menu.loja.test/menu', priority: '0.9' },
      { loc: 'https://menu.loja.test/colecao/rusticos', priority: '0.7' },
      { loc: 'https://menu.loja.test/produto/PH', priority: '0.8' },
      { loc: 'https://menu.loja.test/produto/CROIS%2001', priority: '0.8' },
      { loc: 'https://menu.loja.test/faq', priority: '0.6' },
      { loc: 'https://menu.loja.test/privacy', priority: '0.2' },
      { loc: 'https://menu.loja.test/terms', priority: '0.2' }
    ])
  })

  it('catálogo indisponível ainda publica as rotas fixas', () => {
    const locs = sitemapUrls({ origin: 'http://localhost:3000', collectionRefs: [], skus: [] }).map(url => url.loc)
    expect(locs).toEqual([
      'http://localhost:3000/',
      'http://localhost:3000/menu',
      'http://localhost:3000/faq',
      'http://localhost:3000/privacy',
      'http://localhost:3000/terms'
    ])
  })

  it('escreve XML válido, escapando o que precisa', () => {
    const xml = sitemapXml([{ loc: 'https://x.test/produto/A&B', priority: '0.8' }])
    expect(xml).toBe(
      '<?xml version="1.0" encoding="UTF-8"?>\n'
      + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
      + '  <url><loc>https://x.test/produto/A&amp;B</loc><priority>0.8</priority></url>\n'
      + '</urlset>\n'
    )
  })
})
