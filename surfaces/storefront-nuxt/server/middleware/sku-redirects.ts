import { defineEventHandler, useRuntimeConfig } from '#imports'
import { resolveDjangoBaseUrl } from '../utils/djangoBaseUrl'
import { redirectRetiredSku } from '../utils/skuRedirects'

export default defineEventHandler(async (event) => {
  await redirectRetiredSku(event, async () => {
    const base = resolveDjangoBaseUrl(useRuntimeConfig().djangoBaseUrl)
    const payload = await $fetch<{ redirects?: Record<string, string> }>(
      `${base}/api/v1/storefront/sku-redirects/`,
      { timeout: 4000 }
    )
    return payload?.redirects || {}
  })
})
