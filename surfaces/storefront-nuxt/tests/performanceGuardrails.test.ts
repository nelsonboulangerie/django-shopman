import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = (path: string) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

describe('storefront performance guardrails', () => {
  it('keeps the global shell independent from the catalog-heavy home', () => {
    const shell = source('app/app.vue')
    const home = source('app/pages/index.vue')
    const shellComposable = source('app/composables/useStorefrontShell.ts')
    const homeComposable = source('app/composables/useStorefrontHome.ts')

    expect(shell).toContain('await useStorefrontShell()')
    expect(shell).not.toContain('useStorefrontHome()')
    expect(home).toContain('await useStorefrontHome()')
    expect(shellComposable).toContain("STOREFRONT_SHELL_KEY = 'shopman-shell'")
    expect(shellComposable).toContain("apiPath('/api/v1/storefront/shell/')")
    expect(homeComposable).toContain("STOREFRONT_HOME_KEY = 'shopman-page-home'")
    expect(`${shell}\n${home}`).not.toContain("apiPath('/api/v1/storefront/home/')")
    const menu = source('app/pages/menu.vue')
    expect(menu).toContain("apiPath('/api/v1/storefront/catalog/')")
    expect(menu).not.toContain("apiPath('/api/v1/storefront/menu/')")
    expect(menu).toContain('const canonicalOnServer = import.meta.server')
    expect(menu).toContain('lazy: import.meta.client || !canonicalOnServer')
  })

  it('feeds the sitemap from the public catalog twin, not the personalized menu', () => {
    const sitemap = source('server/routes/sitemap.xml.ts')
    expect(sitemap).toContain('/api/v1/storefront/public/catalog/')
    expect(sitemap).not.toContain('/api/v1/storefront/menu/')
  })

  it('does not precache every iOS splash screen', () => {
    expect(source('nuxt.config.ts')).toContain("'pwa/apple-splash-*.png'")
  })

  it('starts navigation tracking at the click but keeps wait UI silent for 200ms', () => {
    const shell = source('app/app.vue')
    const feedback = source('app/components/NavigationFeedback.vue')

    expect(shell).toContain('<NavigationFeedback />')
    expect(feedback).toContain("document.addEventListener('click', navigationIntent, true)")
    expect(feedback).toContain("nuxtApp.hook('page:finish', finish)")
    expect(feedback).toContain("aria-live=\"polite\"")
    expect(feedback).toContain('const WAIT_THRESHOLD_MS = 200')
    expect(feedback).toContain('data-navigation-wait-overlay')
    expect(feedback).toContain('data-navigation-wait-card')
    expect(feedback).toContain('pointer-events-none')
    expect(feedback).not.toContain('event.stopImmediatePropagation()')
    expect(feedback).not.toContain('event.preventDefault()')
    expect(feedback).toContain('Abrindo sua sacola…')
    expect(feedback).toContain('blur(4px)')
    expect(feedback).toContain('blur(24px)')
    expect(feedback).not.toContain('data-navigation-origin-feedback')
    expect(feedback).not.toContain('data-navigation-delayed-feedback')
    expect(feedback).not.toContain('fixed inset-x-0 top-0')
  })

  it('mounts route content before slow page projections finish', () => {
    const cart = source('app/pages/sacola.vue')
    const home = source('app/composables/useStorefrontHome.ts')
    const continuum = source('app/composables/useContinuousProjection.ts')
    const lazyPages = [
      'app/pages/busca.vue',
      'app/pages/colecao/[ref].vue',
      'app/pages/produto/[sku].vue',
      'app/pages/finalizar.vue',
      'app/pages/pedido/[ref]/index.vue',
      'app/pages/privacidade.vue',
      'app/pages/termos.vue',
      'app/pages/conta/index.vue',
      'app/pages/conta/perfil.vue',
      'app/pages/conta/favoritos.vue',
      'app/pages/conta/pedidos.vue',
      'app/pages/conta/preferencias.vue',
      'app/pages/conta/enderecos.vue',
      'app/pages/conta/seguranca.vue'
    ]

    expect(cart).not.toContain("await useFetch<CartResponse>(apiPath('/api/v1/storefront/cart/')")
    expect(cart).toContain('void refreshCart().catch(() => null)')
    expect(home).toContain('lazy: true')
    expect(continuum).toContain('lazy: true')
    for (const path of lazyPages) expect(source(path)).toContain('lazy: true')
    // Página preguiçosa avisa o NavigationFeedback que ainda espera o próprio
    // dado; sem isto o page:finish cancela o aviso antes dos 200 ms.
    for (const path of [...lazyPages, 'app/pages/menu.vue', 'app/pages/index.vue']) {
      expect(source(path), path).toContain('useNavigationPending(')
    }
    expect(source('app/components/NavigationFeedback.vue')).toContain('useNavigationPendingRegistry()')
  })

  it('guards checkout against a second in-flight submit', () => {
    const checkout = source('app/pages/finalizar.vue')
    const guard = checkout.indexOf('if (submitting.value || !checkout.value || !validate()) return')
    const mutation = checkout.indexOf('submitting.value = true', guard)

    expect(guard).toBeGreaterThan(-1)
    expect(mutation).toBeGreaterThan(guard)
  })
})
