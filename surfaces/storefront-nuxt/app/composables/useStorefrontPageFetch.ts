import type { StorefrontSsrRead } from '../../shared/types/ssrRead'
import { reuseSsrRead } from '#shared/utils/ssrRead'

/** Reaproveita apenas a promessa desta requisição SSR, nunca de outra visita. */
export function useStorefrontPageFetch (): typeof $fetch | undefined {
  if (import.meta.client) return undefined
  const state = useRequestEvent()?.context.storefrontSsrRead as StorefrontSsrRead | undefined
  return reuseSsrRead(state, useRequestFetch())
}
