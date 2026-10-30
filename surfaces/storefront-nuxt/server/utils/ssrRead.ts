import type { $Fetch, FetchContext, FetchOptions } from 'ofetch'
import type { StorefrontSsrRead, SsrReadTiming } from '../../shared/types/ssrRead'

/** Só antecipa as leituras que estas páginas já fazem; não cria outra API. */
export function ssrProjectionPath (pathname: string, baseURL = '/', continuum: unknown = false) {
  const base = baseURL.replace(/\/+$/, '')
  if (base && !pathname.startsWith(base + '/')) return null
  const path = base ? pathname.slice(base.length) : pathname
  if (/^\/menu\/?$/.test(path)) {
    if (continuum === true || String(continuum || '').toLowerCase() === 'true') {
      return { route: 'catalog' as const, path: `${base}/api/v1/storefront/continuum/v0.2/catalog-structure/`,
        format: 'snapshot' as const, fallbackPath: `${base}/api/v1/storefront/catalog/` }
    }
    return { route: 'catalog' as const, path: `${base}/api/v1/storefront/catalog/` }
  }
  const match = /^\/produto\/([^/]+)\/?$/.exec(path)
  if (!match) return null
  try {
    return { route: 'product' as const, path: `${base}/api/v1/storefront/products/${encodeURIComponent(decodeURIComponent(match[1]!))}/` }
  } catch { return null }
}

const ERROR_CODES = new Set([
  'ECONNRESET', 'ECONNREFUSED', 'ENOTFOUND', 'ETIMEDOUT', 'EPIPE',
  'UND_ERR_SOCKET', 'UND_ERR_CONNECT_TIMEOUT', 'UND_ERR_HEADERS_TIMEOUT',
  'ABORT_ERR', 'TimeoutError', 'AbortError', 'upstream_timeout', 'upstream_unreachable'
])

export function publicSsrReadOptions (): FetchOptions<'json'> {
  return {
    method: 'GET', credentials: 'include', retry: 1, retryDelay: 200,
    onResponse: (context) => {
      const retryAfter = context.response.headers.get('retry-after')?.trim()
      // Não repetir um bloqueio por limite, nem contrariar a janela de espera
      // declarada pelo backend. Só a leitura pública sem efeito é antecipada.
      if (context.response.status === 429 || (retryAfter && retryAfter !== '0')) context.options.retry = 0
    }
  }
}

/** Nada de mensagens, URLs, payloads, cookies ou tokens na telemetria. */
export function ssrErrorCode (error: unknown): string | undefined {
  let current = error
  for (let depth = 0; depth < 4 && current && typeof current === 'object'; depth++) {
    const value = current as { code?: unknown, name?: unknown, data?: { error_code?: unknown }, cause?: unknown }
    for (const candidate of [value.data?.error_code, value.code, value.name]) {
      if (typeof candidate === 'string' && ERROR_CODES.has(candidate)) return candidate
    }
    current = value.cause
  }
  return undefined
}

export function traceSsrFetch<T extends (...args: never[]) => Promise<unknown>> (fetcher: T, state: StorefrontSsrRead, clock = () => performance.now()): T {
  // Mantém a assinatura genérica de rotas do fetch original; o observador não
  // transforma o corpo nem os erros devolvidos por ele.
  const transport = fetcher as unknown as $Fetch
  const observe = async (request: Parameters<$Fetch>[0], options?: FetchOptions, raw = false) => {
    const send = (request: Parameters<$Fetch>[0], options?: FetchOptions) => raw ? transport.raw(request, options) : transport(request, options)
    const path = typeof request === 'string' ? request.split('?')[0] : ''
    const kind = path === state.primaryPath ? 'primary' : path === state.fallbackPath ? 'fallback'
      : path?.endsWith('/api/v1/storefront/site/') ? 'site'
        : path?.endsWith('/api/v1/storefront/shell/') ? 'shell' : null
    if (!kind) return send(request, options)
    const read: SsrReadTiming = { kind, startedAt: clock(), statuses: [] }
    state.reads.push(read)
    const hooks = options?.onResponse ? [options.onResponse].flat() : []
    const requestErrorHooks = options?.onRequestError ? [options.onRequestError].flat() : []
    try {
      return await send(request, {
        ...options,
        onResponse: [...hooks, (context: FetchContext) => {
          if (context.response) {
            read.statuses.push(context.response.status)
            const code = /(?:^|,\s*)upstream_error;desc="([A-Za-z_]+)"/.exec(context.response.headers.get('server-timing') || '')?.[1]
            if (code && ERROR_CODES.has(code)) (read.networkCodes ||= []).push(code)
          }
        }],
        onRequestError: [...requestErrorHooks, (context: FetchContext) => {
          const code = ssrErrorCode(context.error)
          if (code) (read.networkCodes ||= []).push(code)
        }]
      })
    } catch (error) {
      read.errorCode = ssrErrorCode(error)
      throw error
    } finally { read.finishedAt = clock() }
  }
  const traced = (request: Parameters<$Fetch>[0], options?: FetchOptions) => observe(request, options)
  const raw = (request: Parameters<$Fetch>[0], options?: FetchOptions) => observe(request, options, true)
  return Object.assign(traced, fetcher, { raw }) as unknown as T
}

export function ssrReadSnapshot (state: StorefrontSsrRead, now = performance.now()) {
  return {
    category: 'storefront_ssr_observation', request_id: state.id, route: state.route,
    duration_ms: Math.round(Math.max(0, now - state.startedAt) * 100) / 100,
    reads: state.reads.map(read => ({
      kind: read.kind,
      start_ms: Math.round(Math.max(0, read.startedAt - state.startedAt) * 100) / 100,
      duration_ms: Math.round(Math.max(0, (read.finishedAt ?? now) - read.startedAt) * 100) / 100,
      completed: read.finishedAt !== undefined,
      statuses: [...read.statuses],
      ...(read.errorCode ? { error_code: read.errorCode } : {}),
      ...(read.networkCodes?.length ? { network_codes: [...read.networkCodes] } : {})
    }))
  }
}
