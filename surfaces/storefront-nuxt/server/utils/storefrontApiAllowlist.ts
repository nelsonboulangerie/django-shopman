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
  // ⚠️ O catch-all do Nitro entrega `/api/v1/checkout/` como `checkout` (sem a
  // barra final), e `"checkout".startsWith("checkout/")` é false — o endpoint
  // RAIZ de cada prefixo tomava 404 no BFF enquanto os subcaminhos passavam.
  // Foi assim que o "Enviar pedido" da loja quebrou em silêncio (o commit do
  // checkout é POST /api/v1/checkout/, o único endpoint raiz com tráfego).
  // A igualdade sem a barra readmite a raiz; `checkoutX` continua bloqueado.
  return STOREFRONT_API_PREFIXES.some(
    (prefix) => normalized.startsWith(prefix) || normalized === prefix.slice(0, -1)
  )
}
