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
