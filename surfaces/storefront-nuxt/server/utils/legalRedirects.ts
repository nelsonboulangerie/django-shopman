// ENDEREÇO QUE MUDOU MERECE 301, NÃO 404 — agora nas páginas legais.
//
// A loja fala português com o cliente, e as rotas dela são `/conta`, `/sacola`,
// `/finalizar`. Privacidade e Termos eram as duas exceções em inglês até 24/09/2026.
// O site é público e indexado, e os endereços antigos podem estar cadastrados fora
// daqui (tela de consentimento OAuth do Google, Search Console, bio, ManyChat): por
// isso eles respondem 301 para sempre, em vez de sumirem.
//
// Vira `routeRules` no `nuxt.config.ts`: o Nitro responde antes de montar a página,
// e leva a query junto (`/terms?utm_source=x` → `/termos?utm_source=x`). A âncora
// (`#cancellation`) nem chega ao servidor; o navegador a mantém no destino.

export const LEGAL_ROUTE_REDIRECTS = {
  '/privacy': '/privacidade',
  '/terms': '/termos'
} as const

type RedirectRule = { redirect: { to: string, statusCode: 301 } }

export function legalRedirectRules (): Record<string, RedirectRule> {
  const rules: Record<string, RedirectRule> = {}
  for (const [from, to] of Object.entries(LEGAL_ROUTE_REDIRECTS)) {
    rules[from] = { redirect: { to, statusCode: 301 } }
  }
  return rules
}
