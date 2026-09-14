export const STOREFRONT_PWA_FALLBACK = {
  brand_name: 'Nelson Boulangerie',
  short_name: 'Nelson',
  description: 'Padaria artesanal brasileira inspirada na panificação francesa.',
  theme_color: '#7C3A40',
  background_color: '#FCF7EE'
} as const

export interface PwaShopSource {
  brand_name?: string | null
  short_name?: string | null
  description?: string | null
  theme_color?: string | null
  background_color?: string | null
}

function textOrFallback (value: string | null | undefined, fallback: string): string {
  return value?.trim() || fallback
}

export function shortPwaName (shop: PwaShopSource): string {
  const explicit = shop.short_name?.trim()
  if (explicit) return explicit.slice(0, 12).trimEnd()
  const brandName = shop.brand_name?.trim()
  if (!brandName) return STOREFRONT_PWA_FALLBACK.short_name
  return brandName
    .slice(0, 12)
    .trimEnd()
}

export function buildStorefrontManifest (shop: PwaShopSource = {}) {
  const name = textOrFallback(shop.brand_name, STOREFRONT_PWA_FALLBACK.brand_name)

  return {
    id: '/',
    name,
    short_name: shortPwaName(shop),
    description: textOrFallback(shop.description, STOREFRONT_PWA_FALLBACK.description),
    lang: 'pt-BR',
    dir: 'ltr',
    start_url: '/?source=pwa',
    scope: '/',
    display: 'standalone',
    display_override: ['standalone'],
    orientation: 'portrait',
    theme_color: textOrFallback(shop.theme_color, STOREFRONT_PWA_FALLBACK.theme_color),
    background_color: textOrFallback(shop.background_color, STOREFRONT_PWA_FALLBACK.background_color),
    icons: [
      { src: '/pwa/pwa-64x64.png', sizes: '64x64', type: 'image/png', purpose: 'any' },
      { src: '/pwa/pwa-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/pwa/pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/pwa/maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
      { src: '/pwa/monochrome-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'monochrome' }
    ],
    shortcuts: [
      { name: 'Cardápio', short_name: 'Cardápio', url: '/menu', icons: [{ src: '/pwa/pwa-192x192.png', sizes: '192x192' }] },
      { name: 'Sacola', short_name: 'Sacola', url: '/sacola', icons: [{ src: '/pwa/pwa-192x192.png', sizes: '192x192' }] },
      { name: 'Meus pedidos', short_name: 'Pedidos', url: '/conta', icons: [{ src: '/pwa/pwa-192x192.png', sizes: '192x192' }] }
    ],
    categories: ['food', 'shopping']
  }
}
