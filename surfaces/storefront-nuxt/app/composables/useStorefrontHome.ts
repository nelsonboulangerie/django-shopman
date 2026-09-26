import type { NuxtApp } from '#app'
import type { HomeResponse } from '~/types/shopman'

export const STOREFRONT_HOME_KEY = 'shopman-shell-home'

function readCachedHome (
  key: string,
  nuxtApp: NuxtApp,
  context: { cause: string }
): HomeResponse | undefined {
  if (context.cause === 'refresh:manual') return undefined
  return nuxtApp.payload.data[key] as HomeResponse | undefined
}

/**
 * Projeção canônica da casa, sessão e sacola usada pelo shell e pela home.
 *
 * Compartilhar a chave é importante: o shell já precisa desses dados antes de
 * renderizar qualquer página. A rota `/` não deve pedir a mesma projeção pesada
 * outra vez, e consumidores tardios (como o login) podem reaproveitar o payload.
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
