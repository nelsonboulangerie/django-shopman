import {
  getRequestHeader,
  setResponseHeaders,
  type H3Event
} from 'h3'
import {
  buildStorefrontManifest,
  STOREFRONT_PWA_FALLBACK,
  type PwaShopSource
} from '../utils/pwaManifest'

interface HomeShopResponse {
  home?: { shop?: PwaShopSource }
}

async function publicShop (event: H3Event): Promise<PwaShopSource> {
  try {
    const response = await event.$fetch<HomeShopResponse>('/api/v1/storefront/home/', {
      headers: { accept: 'application/json' }
    })
    return response.home?.shop || STOREFRONT_PWA_FALLBACK
  } catch {
    return STOREFRONT_PWA_FALLBACK
  }
}

export default defineEventHandler(async (event) => {
  setResponseHeaders(event, {
    vary: 'User-Agent',
    // Shared CDNs may ignore Vary: User-Agent; never share this variant.
    'cache-control': 'private, no-store',
    'content-type': 'application/manifest+json; charset=utf-8'
  })
  return buildStorefrontManifest(await publicShop(event), getRequestHeader(event, 'user-agent'))
})
