import { getRequestURL, setResponseHeader, type H3Event } from 'h3'

// O QUE O GOOGLE PODE LER × O QUE ELE PODE GUARDAR — duas perguntas, duas ferramentas.
//
// O robots.txt responde a primeira: proíbe a LEITURA. Ele não tira nada do índice,
// porque o Google não lê o que foi proibido de ler — e por isso nunca vê um
// `noindex` numa página bloqueada. O efeito prático morou no Search Console em
// 13/09/2026: o botão "Entrar" do cabeçalho leva `?next=` com a página atual, e cada
// produto virou uma URL `/entrar?next=/produto/<sku>` "Bloqueada pelo robots.txt" —
// descoberta pelo link, impossível de ler, candidata a entrar no índice sem conteúdo.
//
// Por isso as rotas privadas saem do robots.txt e passam a dizer `noindex` no
// cabeçalho da própria resposta: o Google lê, obedece, e qualquer variante de query
// cai junto. O robots.txt fica só com o que não é página (`/api/`).

/** Rotas que existem para quem compra, não para quem busca. */
export const PRIVATE_ROUTE_PREFIXES = ['/conta', '/finalizar', '/sacola', '/entrar', '/pedido'] as const

/** Caminhos que o crawler não deve nem ler: não são páginas. */
export const CRAWL_DISALLOWED_PREFIXES = ['/api/'] as const

export function isPrivateRoute(pathname: string): boolean {
  return PRIVATE_ROUTE_PREFIXES.some(prefix => pathname === prefix || pathname.startsWith(`${prefix}/`))
}

export function robotsTxt(origin: string): string {
  return [
    'User-agent: *',
    'Allow: /',
    ...CRAWL_DISALLOWED_PREFIXES.map(prefix => `Disallow: ${prefix}`),
    '',
    `Sitemap: ${origin}/sitemap.xml`,
    ''
  ].join('\n')
}

export function applyIndexingPolicy(event: H3Event): void {
  if (isPrivateRoute(getRequestURL(event).pathname)) {
    setResponseHeader(event, 'x-robots-tag', 'noindex')
  }
}
