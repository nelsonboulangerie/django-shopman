// O <head> das páginas do entregador: manifesto próprio (escopo `/rota/`, "Rotas · Nelson"),
// nada de índice e nada de referer (o token do link não vaza para o Waze nem para o mapa).
export const COURIER_MANIFEST_HREF = '/rota/manifest.webmanifest'

export function useCourierPageHead () {
  useHead({
    title: 'Rotas',
    link: [{ key: 'manifest', rel: 'manifest', href: COURIER_MANIFEST_HREF }],
    meta: [
      { key: 'robots', name: 'robots', content: 'noindex, nofollow' },
      { key: 'referrer', name: 'referrer', content: 'no-referrer' },
      { key: 'apple-mobile-web-app-title', name: 'apple-mobile-web-app-title', content: 'Rotas' }
    ]
  })
}
