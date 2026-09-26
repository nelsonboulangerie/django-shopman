import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = (path: string) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

describe('storefront performance guardrails', () => {
  it('shell and home share one canonical home request', () => {
    const shell = source('app/app.vue')
    const home = source('app/pages/index.vue')
    const composable = source('app/composables/useStorefrontHome.ts')

    expect(shell).toContain('await useStorefrontHome()')
    expect(home).toContain('await useStorefrontHome()')
    expect(composable).toContain("STOREFRONT_HOME_KEY = 'shopman-shell-home'")
    expect(`${shell}\n${home}`).not.toContain("apiPath('/api/v1/storefront/home/')")
  })

  it('does not precache every iOS splash screen', () => {
    expect(source('nuxt.config.ts')).toContain("'pwa/apple-splash-*.png'")
  })

  it('starts navigation feedback at the click, before route middleware settles the cart', () => {
    const shell = source('app/app.vue')
    const feedback = source('app/components/NavigationFeedback.vue')

    expect(shell).toContain('<NavigationFeedback />')
    expect(feedback).toContain("document.addEventListener('click', navigationIntent, true)")
    expect(feedback).toContain("nuxtApp.hook('page:finish', finish)")
    expect(feedback).toContain("aria-live=\"polite\"")
  })

  it('guards checkout against a second in-flight submit', () => {
    const checkout = source('app/pages/finalizar.vue')
    const guard = checkout.indexOf('if (submitting.value || !checkout.value || !validate()) return')
    const mutation = checkout.indexOf('submitting.value = true', guard)

    expect(guard).toBeGreaterThan(-1)
    expect(mutation).toBeGreaterThan(guard)
  })
})
