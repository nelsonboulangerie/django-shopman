const DJANGO_TRACKING_RE = /^\/pedido\/([^/?#]+)\/acompanhar\/?(?:([?#].*)?)$/

// Tradução das rotas em inglês emitidas pelo Django para as rotas pt-BR da loja Nuxt.
// O backend continua emitindo os paths em inglês (contrato intocado); esta função é a
// ponte. `(?=$|[/?#])` casa só o prefixo de rota (não pega substrings acidentais).
const BACKEND_ROUTE_MAP: Array<[RegExp, string]> = [
  [/^\/cart(?=$|[/?#])/, '/sacola'],
  [/^\/checkout(?=$|[/?#])/, '/finalizar'],
  [/^\/login(?=$|[/?#])/, '/entrar'],
  [/^\/account(?=$|[/?#])/, '/conta'],
  [/^\/tracking(?=$|[/?#])/, '/pedido'],
]

export function localRouteFromBackend (value: string | null | undefined): string {
  if (!value) return '/'
  if (/^https?:\/\//i.test(value)) return value

  let normalized = value.startsWith('/') ? value : `/${value}`
  const tracking = normalized.match(DJANGO_TRACKING_RE)
  if (tracking) return `/pedido/${tracking[1]}${tracking[2] || ''}`

  for (const [re, replacement] of BACKEND_ROUTE_MAP) {
    if (re.test(normalized)) {
      normalized = normalized.replace(re, replacement)
      break
    }
  }
  return normalized
}

export function orderTrackingRoute (ref: string): string {
  return `/pedido/${encodeURIComponent(ref)}`
}
