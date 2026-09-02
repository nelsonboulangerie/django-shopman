import {
  appendResponseHeader,
  getQuery,
  getRequestHeader,
  readRawBody,
  setResponseHeader,
  setResponseStatus,
  splitCookiesString,
  type H3Event
} from 'h3'
import { withQuery } from 'ufo'
import { warnOnApiVersionMismatch } from './apiVersion'
import { resolveDjangoBaseUrl } from './djangoBaseUrl'

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function shouldSanitizeHtmlError (status: number, contentType: string | null, path: string): boolean {
  return status >= 400 && /^text\/html\b/i.test(contentType || '') && path.startsWith('/api/')
}

export function csrfTokenFromCookieHeader (cookie: string | undefined): string {
  return cookie
    ?.split(';')
    .map(part => part.trim())
    .find(part => part.startsWith('csrftoken='))
    ?.slice('csrftoken='.length) || ''
}

export function mergeSetCookieIntoCookieHeader (cookie: string | undefined, setCookie: string): string {
  const [pair = ''] = setCookie.split(';')
  const [name, ...valueParts] = pair.split('=')
  const value = valueParts.join('=')
  if (!name || value == null) return cookie || ''

  const next = new Map<string, string>()
  for (const part of (cookie || '').split(';')) {
    const [cookieName, ...cookieValue] = part.trim().split('=')
    if (cookieName) next.set(cookieName, cookieValue.join('='))
  }
  next.set(name, value)
  return Array.from(next.entries()).map(([cookieName, cookieValue]) => `${cookieName}=${cookieValue}`).join('; ')
}

export function storefrontSetCookieHeader (setCookie: string): string {
  // Customer storefront cookies are host-only by project contract. The upstream
  // Django request may be served through an API/operator alias; when the Nuxt BFF
  // relays that cookie to the public store host, preserving Domain would either
  // make the browser reject it or broaden the customer's session incorrectly.
  // Keep Path/SameSite/Secure/HttpOnly exactly as Django emitted them.
  return setCookie
    .split(';')
    .filter(part => !/^\s*domain=/i.test(part))
    .join(';')
}

async function ensureDjangoCsrfCookie (event: H3Event, djangoBaseUrl: string, cookie: string | undefined): Promise<{ cookie: string | undefined, token: string }> {
  let token = csrfTokenFromCookieHeader(cookie)
  if (token) return { cookie, token: decodeURIComponent(token) }

  const response = await $fetch.raw(`${djangoBaseUrl}/api/v1/storefront/cart/`, {
    method: 'GET',
    headers: {
      accept: 'application/json',
      ...(cookie ? { cookie } : {})
    },
    ignoreResponseError: true
  })

  let mergedCookie = cookie
  const setCookie = response.headers.get('set-cookie')
  if (setCookie) {
    for (const cookieHeader of splitCookiesString(setCookie)) {
      appendResponseHeader(event, 'set-cookie', storefrontSetCookieHeader(cookieHeader))
      mergedCookie = mergeSetCookieIntoCookieHeader(mergedCookie, cookieHeader)
    }
  }

  token = csrfTokenFromCookieHeader(mergedCookie)
  return { cookie: mergedCookie, token: token ? decodeURIComponent(token) : '' }
}

export async function proxyDjangoApi (event: H3Event, path: string) {
  return proxyDjangoPath(event, `/api/v1/${path}`)
}

export async function proxyDjangoPath (event: H3Event, fullPath: string) {
  const config = useRuntimeConfig(event)
  const djangoBaseUrl = resolveDjangoBaseUrl(config.djangoBaseUrl)
  const method = event.method || 'GET'
  const isUnsafeMethod = UNSAFE_METHODS.has(method.toUpperCase())
  const normalizedPath = fullPath.endsWith('/') ? fullPath : `${fullPath}/`
  const target = withQuery(
    `${djangoBaseUrl}${normalizedPath}`,
    getQuery(event)
  )
  const djangoOrigin = new URL(djangoBaseUrl).origin

  const headers: Record<string, string> = {
    accept: getRequestHeader(event, 'accept') || 'application/json'
  }

  let cookie = getRequestHeader(event, 'cookie')
  if (cookie) headers.cookie = cookie

  const contentType = getRequestHeader(event, 'content-type')
  if (contentType) headers['content-type'] = contentType

  // O IP do cliente tem de atravessar o BFF, senão TODO visitante anônimo vira
  // um balde de rate limit só. O navegador fala com o Nitro same-origin, e o
  // Nitro abre conexão NOVA para o Django: sem repassar o XFF, o único IP que o
  // Django vê é o de saída deste processo — idêntico para todo mundo. Efeito
  // medido: ~20 chamadas em /auth/request-code/ e ninguém mais entra na loja
  // por uma hora; checkout anônimo em 3/min para a loja INTEIRA.
  //
  // Repassar o valor CRU é seguro porque quem lê conta da DIREITA
  // (`doorman.get_client_ip(trusted_proxy_depth)` e o `NUM_PROXIES` do DRF): o
  // edge da plataforma acrescenta o IP real à direita, então um XFF forjado
  // pelo cliente entra à esquerda e não desloca a contagem.
  const forwardedFor = getRequestHeader(event, 'x-forwarded-for')
  if (forwardedFor) headers['x-forwarded-for'] = forwardedFor

  if (isUnsafeMethod) {
    headers.origin = djangoOrigin
    headers.referer = `${djangoOrigin}/`
  }

  const clientCsrfHeader = getRequestHeader(event, 'x-csrftoken') || getRequestHeader(event, 'x-csrf-token')
  const csrfCookie = csrfTokenFromCookieHeader(cookie)
  if (csrfCookie) headers['x-csrftoken'] = decodeURIComponent(csrfCookie)
  else if (clientCsrfHeader) headers['x-csrftoken'] = clientCsrfHeader

  if (isUnsafeMethod && !headers['x-csrftoken']) {
    const csrf = await ensureDjangoCsrfCookie(event, djangoBaseUrl, cookie)
    cookie = csrf.cookie
    if (cookie) headers.cookie = cookie
    if (csrf.token) headers['x-csrftoken'] = csrf.token
  }

  const body = ['GET', 'HEAD'].includes(method)
    ? undefined
    : await readRawBody(event, false)

  const response = await $fetch.raw(target, {
    method,
    headers,
    body,
    ignoreResponseError: true
  })

  // Sanidade de contrato: o Django carimba /api/v1/ com X-API-Version; major
  // divergente vira warning estruturado no Nitro (server/utils/apiVersion.ts,
  // auto-importado) — nunca bloqueia a resposta.
  warnOnApiVersionMismatch(response.headers.get('x-api-version'), { path: normalizedPath })

  const setCookie = response.headers.get('set-cookie')
  if (setCookie) {
    for (const cookieHeader of splitCookiesString(setCookie)) {
      appendResponseHeader(event, 'set-cookie', storefrontSetCookieHeader(cookieHeader))
    }
  }

  setResponseStatus(event, response.status)
  const contentTypeResponse = response.headers.get('content-type')
  if (shouldSanitizeHtmlError(response.status, contentTypeResponse, normalizedPath)) {
    setResponseHeader(event, 'content-type', 'application/json; charset=utf-8')
    return { detail: 'Não foi possível responder agora.' }
  }

  if (contentTypeResponse) setResponseHeader(event, 'content-type', contentTypeResponse)

  const contentDisposition = response.headers.get('content-disposition')
  if (contentDisposition) appendResponseHeader(event, 'content-disposition', contentDisposition)

  return response._data
}
