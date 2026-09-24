import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { LEGAL_ROUTE_REDIRECTS, legalRedirectRules } from '../server/utils/legalRedirects'

const here = (path: string) => fileURLToPath(new URL(path, import.meta.url))

// A loja fala português com o cliente. /privacy e /terms eram as exceções, e o site
// é público e indexado: o endereço antigo continua respondendo, com 301.
describe('páginas legais — endereço antigo', () => {
  it('/privacy e /terms respondem 301 para /privacidade e /termos', () => {
    expect(legalRedirectRules()).toEqual({
      '/privacy': { redirect: { to: '/privacidade', statusCode: 301 } },
      '/terms': { redirect: { to: '/termos', statusCode: 301 } }
    })
  })

  it('o destino é página que existe, e o caminho antigo não é mais página', () => {
    for (const [from, to] of Object.entries(LEGAL_ROUTE_REDIRECTS)) {
      expect(existsSync(here(`../app/pages${to}.vue`)), `${to} sem página`).toBe(true)
      expect(existsSync(here(`../app/pages${from}.vue`)), `${from} voltou a ser página`).toBe(false)
    }
  })

  it('o nuxt.config liga as regras', () => {
    const config = readFileSync(here('../nuxt.config.ts'), 'utf8')
    expect(config).toContain("import { legalRedirectRules } from './server/utils/legalRedirects'")
    expect(config).toContain('...legalRedirectRules()')
  })

  it('nenhum link da loja aponta para o endereço antigo', () => {
    const files = [
      '../app/components/ShopFooter.vue',
      '../app/pages/entrar.vue',
      '../app/pages/a.vue',
      '../app/pages/termos.vue',
      '../app/pages/shopman-marketing.vue'
    ]
    for (const file of files) {
      const source = readFileSync(here(file), 'utf8')
      expect(source, file).not.toMatch(/to="\/(privacy|terms)"/)
    }
  })
})
