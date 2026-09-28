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
    expect(source('app/pages/menu.vue')).toContain("apiPath('/api/v1/storefront/catalog/')")
    expect(source('app/pages/menu.vue')).not.toContain("apiPath('/api/v1/storefront/menu/')")
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
    expect(feedback).toContain('Abrindo sua sacola…')
    expect(feedback).toContain('blur(4px)')
    expect(feedback).toContain('blur(24px)')
    expect(feedback).not.toContain('data-navigation-origin-feedback')
    expect(feedback).not.toContain('data-navigation-delayed-feedback')
    expect(feedback).not.toContain('fixed inset-x-0 top-0')
  })

  it('guards checkout against a second in-flight submit', () => {
    const checkout = source('app/pages/finalizar.vue')
    const guard = checkout.indexOf('if (submitting.value || !checkout.value || !validate()) return')
    const mutation = checkout.indexOf('submitting.value = true', guard)

    expect(guard).toBeGreaterThan(-1)
    expect(mutation).toBeGreaterThan(guard)
  })
})
