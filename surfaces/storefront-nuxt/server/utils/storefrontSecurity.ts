import {
  getRequestHeader,
  getRequestURL,
  setResponseHeaders,
  type H3Event,
} from 'h3'

const ONE_YEAR_SECONDS = 31_536_000

// The storefront needs a wider policy than operator surfaces because address
// selection loads Google Maps and may use device geolocation. These Google
// sources follow its documented allowlist CSP; Stripe sources follow the
// Checkout/Stripe.js integration guide. Nuxt serializes hydration data inline,
// so unsafe-inline remains until the app has per-response nonces.
export const STOREFRONT_CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "base-uri 'self'",
  "connect-src 'self' https://*.googleapis.com https://*.google.com https://*.gstatic.com https://api.stripe.com https://checkout.stripe.com data: blob:",
  "font-src 'self' data: https://fonts.gstatic.com",
  "form-action 'self'",
  "frame-ancestors 'none'",
  'frame-src https://*.google.com https://*.js.stripe.com https://js.stripe.com https://hooks.stripe.com https://checkout.stripe.com',
  "img-src 'self' data: blob: https:",
  "manifest-src 'self'",
  "media-src 'self' blob:",
  "object-src 'none'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://*.googleapis.com https://*.gstatic.com https://*.google.com https://*.ggpht.com https://*.googleusercontent.com https://*.js.stripe.com https://js.stripe.com https://checkout.stripe.com blob:",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "worker-src 'self' blob:",
].join('; ')

export const STOREFRONT_PERMISSIONS_POLICY = [
  'browsing-topics=()',
  'camera=()',
  'geolocation=(self)',
  'microphone=()',
  'payment=(self)',
  'usb=()',
].join(', ')

export function storefrontResponseHeaders(secure: boolean, pathname = ''): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Security-Policy': STOREFRONT_CONTENT_SECURITY_POLICY,
    'Permissions-Policy': STOREFRONT_PERMISSIONS_POLICY,
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
  }
  if (secure) {
    headers['Strict-Transport-Security'] = `max-age=${ONE_YEAR_SECONDS}; includeSubDomains; preload`
  }
  if (pathname === '/gerenciar-aviso') {
    headers['Cache-Control'] = 'private, no-store, max-age=0'
    headers.Pragma = 'no-cache'
    headers['Referrer-Policy'] = 'no-referrer'
  }
  return headers
}

function requestIsHttps(event: H3Event): boolean {
  const forwardedProtocol = getRequestHeader(event, 'x-forwarded-proto')
    ?.split(',', 1)[0]
    ?.trim()
    .toLowerCase()
  if (forwardedProtocol) return forwardedProtocol === 'https'
  return getRequestURL(event).protocol === 'https:'
}

export function applyStorefrontSecurityHeaders(event: H3Event): void {
  const headers = storefrontResponseHeaders(requestIsHttps(event), getRequestURL(event).pathname)
  setResponseHeaders(event, headers)
}
