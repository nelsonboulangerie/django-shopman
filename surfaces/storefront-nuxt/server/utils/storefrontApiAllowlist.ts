const STOREFRONT_API_PREFIXES = [
  'account/',
  'auth/',
  'availability/',
  'cart/',
  'catalog/',
  'checkout/',
  'fomo/',
  'geocode/',
  'offers/',
  'orders/',
  'payment/',
  'storefront/',
  'tracking/',
]

export function normalizeStorefrontApiPath(path: string): string {
  return path.replace(/^\/+/, '')
}

export function isStorefrontApiPathAllowed(path: string): boolean {
  const normalized = normalizeStorefrontApiPath(path)
  return STOREFRONT_API_PREFIXES.some((prefix) => normalized.startsWith(prefix))
}
