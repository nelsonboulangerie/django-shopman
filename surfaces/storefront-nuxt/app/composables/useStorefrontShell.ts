import type { NuxtApp } from '#app'
import type { ShellResponse } from '~/types/shopman'
import { hasNonDefaultExperience, privateDocumentCacheControl } from '~/utils/experience'

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
  const requestFetch = import.meta.server ? useRequestFetch() : $fetch
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined
  // X14 na borda do Nitro: o documento SSR embute o shell no payload. Se o shell
  // traz uma versão de experimento fora da padrão, o HTML é de UMA pessoa e sai
  // `private, no-store`, como a resposta da API que o originou.
  const documentCacheControl = import.meta.server ? useResponseHeader('Cache-Control') : undefined

  return useAsyncData<ShellResponse>(
    STOREFRONT_SHELL_KEY,
    async () => {
      const shell = await requestFetch<ShellResponse>(apiPath('/api/v1/storefront/shell/'), {
        credentials: 'include',
        headers
      })
      if (documentCacheControl && hasNonDefaultExperience(shell)) {
        documentCacheControl.value = privateDocumentCacheControl(documentCacheControl.value)
      }
      return shell
    },
    {
      server: true,
      dedupe: 'defer',
      getCachedData: readCachedShell
    }
  )
}
