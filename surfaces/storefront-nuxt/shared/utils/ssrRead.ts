import type { $Fetch, FetchOptions } from 'ofetch'
import type { StorefrontSsrRead } from '../types/ssrRead'

export function reuseSsrRead<T extends (...args: never[]) => unknown> (state: StorefrontSsrRead | undefined, fallback: T): T | undefined {
  if (!state?.primary) return undefined
  const transport = fallback as unknown as $Fetch
  const prefetched = (request: Parameters<$Fetch>[0], options?: FetchOptions) => {
    if (request === state.primaryPath && (!options?.method || String(options.method).toUpperCase() === 'GET')
      && !options?.body && !options?.query && !options?.params && !options?.headers) return state.primary!
    return transport(request, options)
  }
  return Object.assign(prefetched, fallback) as unknown as T
}

/** Reusa a resposta completa: ETag, status e corpo conservam o contrato Continuum. */
export function reuseSsrRawRead<T extends (...args: never[]) => unknown> (state: StorefrontSsrRead | undefined, fallback: T): T {
  if (!state?.primaryRaw) return fallback
  const transport = fallback as unknown as $Fetch['raw']
  const prefetched = (request: Parameters<$Fetch>[0], options?: FetchOptions) => {
    const headers = new Headers(options?.headers)
    const names = [...headers.keys()]
    if (request === state.primaryPath && (!options?.method || String(options.method).toUpperCase() === 'GET')
      && options?.credentials === 'omit' && options.ignoreResponseError === true
      && !options.body && !options.query && !options.params && !options.responseType
      && names.length === 1 && names[0] === 'accept'
      && headers.get('accept') === 'application/cloudevents+json; continuum=0.2; schema=1') return state.primaryRaw!
    return transport(request, options)
  }
  return prefetched as unknown as T
}
