import { normalizeSite } from '~/presentation/seo'
import type { SiteProjection, SiteResponse } from '~/types/shopman'
import type { NuxtApp } from '#app'

// Identidade pública do site (títulos por página, verificações de domínio,
// LocalBusiness, FAQ) — GET /api/v1/storefront/site/, anônimo.
//
// UMA busca por request: o shell (app.vue) e as páginas chamam este composable
// com a mesma chave, e o `useAsyncData` compartilha o estado. Três detalhes
// seguram isso:
//   - `dedupe: 'defer'` — a segunda chamada, com a primeira ainda em voo, espera
//     a mesma promessa em vez de cancelá-la e recomeçar;
//   - `getCachedData` lê o payload — no servidor, a página que chega depois do
//     shell reaproveita o que ele já trouxe; no cliente, a navegação não refaz;
//   - o handler NUNCA rejeita: sem o endpoint (a loja no ar ainda não tem) ou com
//     erro, devolve `{ site: null }` e cada página cai no padrão de antes. Um
//     erro aqui não pode derrubar a página que só queria um título melhor.
export const SITE_SEO_KEY = 'shopman-site-seo'

interface SiteSeoState {
  site: SiteProjection | null
}

function readCachedSite (key: string, nuxtApp: NuxtApp, context: { cause: string }): SiteSeoState | undefined {
  if (context.cause === 'refresh:manual') return undefined
  return nuxtApp.payload.data[key] as SiteSeoState | undefined
}

function emptySite (): SiteSeoState {
  return { site: null }
}

export function useSiteSeo () {
  const apiPath = useShopmanApiPath()
  const url = apiPath('/api/v1/storefront/site/')
  const request = useAsyncData<SiteSeoState>(
    SITE_SEO_KEY,
    () => $fetch<SiteResponse>(url)
      .then(response => ({ site: normalizeSite(response?.site) }))
      .catch(() => ({ site: null })),
    {
      server: true,
      dedupe: 'defer',
      default: emptySite,
      getCachedData: readCachedSite
    }
  )
  const site = computed<SiteProjection | null>(() => request.data.value?.site ?? null)
  const ready = Promise.resolve(request).then(() => undefined)
  return { site, ready }
}
