import { describe, expect, it } from 'vitest'
import { createApp, eventHandler, toWebHandler } from 'h3'
import { applyIndexingPolicy, isPrivateRoute, robotsTxt } from '../server/utils/indexingPolicy'

// Search Console, 13/09/2026: `/entrar?next=/produto/<sku>` "Bloqueada pelo
// robots.txt". Rota privada se declara `noindex`; o robots.txt não a esconde mais.

function handle() {
  const app = createApp().use(eventHandler((event) => {
    applyIndexingPolicy(event)
    return 'ok'
  }))
  return toWebHandler(app)
}

describe('indexing policy', () => {
  it('robots.txt deixa o Google ler as rotas privadas para ele ver o noindex', () => {
    const body = robotsTxt('https://loja.test')

    for (const route of ['/entrar', '/conta', '/sacola', '/finalizar', '/pedido/']) {
      expect(body).not.toContain(`Disallow: ${route}`)
    }
    expect(body).toContain('Disallow: /api/')
    expect(body).toContain('Sitemap: https://loja.test/sitemap.xml')
  })

  it.each([
    '/entrar?next=%2Fproduto%2FPH',
    '/conta',
    '/conta/pedidos',
    '/sacola',
    '/finalizar',
    '/pedido/NB-123',
  ])('%s responde noindex no cabeçalho', async (path) => {
    const response = await handle()(new Request(`https://loja.test${path}`))
    expect(response.headers.get('x-robots-tag')).toBe('noindex')
  })

  it.each(['/', '/menu', '/produto/PH', '/colecao/paes', '/contato', '/entrarx', '/pedidos-especiais'])(
    '%s continua indexável',
    async (path) => {
      expect(isPrivateRoute(path)).toBe(false)
      const response = await handle()(new Request(`https://loja.test${path}`))
      expect(response.headers.get('x-robots-tag')).toBeNull()
    },
  )
})
