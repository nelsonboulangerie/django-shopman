import type { NuxtApp } from '#app'
import type { HomeResponse } from '~/types/shopman'

export const STOREFRONT_HOME_KEY = 'shopman-page-home'

function readCachedHome (
  key: string,
  nuxtApp: NuxtApp,
  context: { cause: string }
): HomeResponse | undefined {
  if (context.cause === 'refresh:manual') return undefined
  return nuxtApp.payload.data[key] as HomeResponse | undefined
}

/**
 * Projeção completa exclusiva da home, incluindo catálogo e histórico.
 * O shell global usa `useStorefrontShell`; compartilhar esta projeção pesada
 * com todas as rotas faria cada página reconstruir o catálogo antes do SSR.
 */
export function useStorefrontHome () {
  const apiPath = useShopmanApiPath()
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined

  return useAsyncData<HomeResponse>(
    STOREFRONT_HOME_KEY,
    () => $fetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
      credentials: 'include',
      headers
    }),
    {
      server: true,
      dedupe: 'defer',
      getCachedData: readCachedHome
    }
  )
}
