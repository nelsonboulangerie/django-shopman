import {
  getRequestHeader,
  getRequestURL,
  getResponseHeader,
  setResponseHeader,
  setResponseHeaders,
  type H3Event,
} from 'h3'
import { hasDjangoSession } from './djangoProxy'
import { headerValue, setHeaderValue, type RenderHeaders } from './homeCompression'

const ONE_YEAR_SECONDS = 31_536_000

// The storefront needs a wider policy than operator surfaces because address
// selection loads Google Maps and may use device geolocation. These Google
// sources follow its documented allowlist CSP; Stripe sources follow the
// Checkout/Stripe.js integration guide. Nuxt serializes hydration data inline,
// so unsafe-inline remains until the app has per-response nonces.
export const STOREFRONT_CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "base-uri 'self'",
  // viacep.com.br: a busca do endereço pelo CEP (AddressPicker), a mesma do PDV.
  "connect-src 'self' https://*.googleapis.com https://*.google.com https://*.gstatic.com https://api.stripe.com https://checkout.stripe.com https://viacep.com.br data: blob:",
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

// Documentos HTML que carregam dado de UMA pessoa no SSR (laudo 23/10, U7): o
// pedido, a conta, a sacola, o checkout, a entrada e o link de acesso. Sem
// `private, no-store`, um cache compartilhado (borda, proxy corporativo) ou o
// histórico do navegador num dispositivo emprestado podia servir o pedido de um
// cliente a outro. O cardápio, a home, o produto e as páginas legais ficam de
// fora quando ANÔNIMOS: aí são públicos e continuam cacheáveis. Com sessão, todo
// documento é privado (`sessionDocumentHeaders`, abaixo).
const PERSONAL_DOCUMENT_PREFIXES = ['/pedido', '/conta'] as const
const PERSONAL_DOCUMENT_PATHS = new Set(['/sacola', '/finalizar', '/entrar', '/a'])

export function isPersonalDocumentPath(pathname: string): boolean {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  if (PERSONAL_DOCUMENT_PATHS.has(path)) return true
  return PERSONAL_DOCUMENT_PREFIXES.some(prefix => path === prefix || path.startsWith(`${prefix}/`))
}

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
  // Páginas que carregam uma capacidade no fragmento (#…): nunca em cache, nunca em referrer.
  if (pathname === '/gerenciar-aviso' || pathname === '/encerrar-acesso' || pathname === '/liberar-acesso') {
    headers['Cache-Control'] = 'private, no-store, max-age=0'
    headers.Pragma = 'no-cache'
    headers['Referrer-Policy'] = 'no-referrer'
  }
  if (isPersonalDocumentPath(pathname)) {
    headers['Cache-Control'] = 'private, no-store'
  }
  if (pathname === '/sw.js') {
    headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
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

// ── Documento com sessão: privado em TODA rota (#3474) ───────────────────────
//
// O documento SSR embute o shell no payload do Nuxt: o nome da cliente
// (`omotenashi.customer_name`), a sacola e a versão de experimento que o servidor
// decidiu para ela (X14). Com o cookie de sessão do Django, nenhuma página é de
// todos, nem o cardápio, nem o produto, nem a página legal: o HTML sai `private,
// no-store`. A regra é da SESSÃO, não da rota, e mora num ponto só (o
// `render:response` do `plugins/securityHeaders.ts`), para que rota nova nasça
// coberta sem ninguém lembrar dela.
//
// Anônimo não muda: sem sessão, o documento é o do visitante (o shell vem da
// gêmea pública, `publicTwinPath`) e segue com a política de cada rota.
//
// A Cloudflare ignora `Vary: Cookie` (shopman/storefront/api/public_cache.py),
// por isso a separação é pelo `Cache-Control` do documento com sessão, e não por
// `Vary`: `no-store` já proíbe qualquer cópia, com ou sem `Vary`.

const SHARED_CACHE_DIRECTIVES = new Set(['public', 'private', 'no-store', 'no-cache', 'max-age', 's-maxage', 'stale-while-revalidate', 'stale-if-error', 'immutable', 'must-revalidate', 'proxy-revalidate'])

/**
 * `private, no-store`, preservando o que não fala de guarda (o `no-transform` da
 * home, que segura a ofuscação de e-mail da Cloudflare). O que já é `private,
 * no-store` fica como está (o `max-age=0` das páginas de capacidade).
 */
export function privateDocumentCacheControl(existing: unknown): string {
  const current = String(existing ?? '').trim()
  const directives = new Set(current.split(',').map(part => part.split('=')[0]!.trim().toLowerCase()))
  if (directives.has('private') && directives.has('no-store') && !directives.has('public')) return current
  const kept = String(existing ?? '')
    .split(',')
    .map(part => part.trim())
    .filter(Boolean)
    .filter(part => !SHARED_CACHE_DIRECTIVES.has(part.split('=')[0]!.trim().toLowerCase()))
  return ['private', 'no-store', ...kept].join(', ')
}

function setCookieNames(setCookie: unknown): string[] {
  const values = Array.isArray(setCookie) ? setCookie : [setCookie]
  return values
    .map(value => String(value ?? '').split(';', 1)[0]!.split('=', 1)[0]!.trim())
    .filter(Boolean)
}

/**
 * Este documento é de uma sessão? O navegador mandou o cookie de sessão do
 * Django, ou a própria resposta está criando um (a sessão que nasce no render
 * também é de alguém).
 */
export function documentCarriesSession(cookie: string | undefined, setCookie: unknown): boolean {
  if (hasDjangoSession(cookie)) return true
  return setCookieNames(setCookie).some(name => hasDjangoSession(`${name}=`))
}

/**
 * Carimba o documento renderizado com sessão como `private, no-store`.
 *
 * Lê o `Cache-Control` que já existe (o da resposta montada ou o da regra de rota
 * no evento) e o reescreve nos dois lugares, sem depender da caixa do nome.
 * Devolve se carimbou.
 */
export function applySessionDocumentHeaders(headers: RenderHeaders, event: H3Event): boolean {
  const setCookie = headerValue(headers, 'set-cookie') ?? getResponseHeader(event, 'set-cookie')
  if (!documentCarriesSession(getRequestHeader(event, 'cookie'), setCookie)) return false
  const existing = headerValue(headers, 'cache-control') ?? getResponseHeader(event, 'cache-control')
  const value = privateDocumentCacheControl(existing)
  setHeaderValue(headers, 'Cache-Control', value)
  setResponseHeader(event, 'Cache-Control', value)
  return true
}
