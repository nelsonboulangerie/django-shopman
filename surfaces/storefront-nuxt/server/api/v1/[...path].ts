import { createError } from 'h3'
import { proxyDjangoApi } from '../../utils/djangoProxy'
import { isStorefrontApiPathAllowed, normalizeStorefrontApiPath } from '../../utils/storefrontApiAllowlist'

export default defineEventHandler((event) => {
  const rawPath = event.context.params?.path || ''
  const path = normalizeStorefrontApiPath(Array.isArray(rawPath) ? rawPath.join('/') : rawPath)
  if (!isStorefrontApiPathAllowed(path)) {
    throw createError({ statusCode: 404, statusMessage: 'Not Found' })
  }
  return proxyDjangoApi(event, path)
})
