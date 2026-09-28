import type { NuxtApp } from '#app'
import type { ShellResponse } from '~/types/shopman'

export const STOREFRONT_SHELL_KEY = 'shopman-shell'

function readCachedShell (
  key: string,
  nuxtApp: NuxtApp,
  context: { cause: string }
): ShellResponse | undefined {
  if (context.cause === 'refresh:manual') return undefined
  return nuxtApp.payload.data[key] as ShellResponse | undefined
}

/** Estado global da loja, sem catálogo, destaques nem histórico de pedidos. */
export function useStorefrontShell () {
  const apiPath = useShopmanApiPath()
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined

  return useAsyncData<ShellResponse>(
    STOREFRONT_SHELL_KEY,
    () => $fetch<ShellResponse>(apiPath('/api/v1/storefront/shell/'), {
      credentials: 'include',
      headers
    }),
    {
      server: true,
      dedupe: 'defer',
      getCachedData: readCachedShell
    }
  )
}
