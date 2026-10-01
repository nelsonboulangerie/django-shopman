function readCookie (name: string): string {
  if (!import.meta.client) return ''
  const prefix = `${name}=`
  return document.cookie
    .split(';')
    .map(part => part.trim())
    .find(part => part.startsWith(prefix))
    ?.slice(prefix.length) || ''
}

// Só repassa o token que o navegador JÁ tem. Não semeia: quem semeia é o BFF
// (`server/utils/djangoProxy.ts`, `ensureDjangoCsrfCookie`), que já faz isso na
// própria mutação e devolve o `Set-Cookie` ao navegador. A semente que morava
// aqui era uma ida a mais só no primeiro clique (GET da sacola inteira antes do
// PUT) e engolia o erro em silêncio: a falha aparecia longe da causa, como o
// toast genérico do carrinho. Ver docs/reports/go-live-acceleration-20260929/
// 04-bug-segundo-clique.md, achado A.
export function useShopmanCsrfHeaders () {
  return async function csrfHeaders (): Promise<Record<string, string>> {
    if (!import.meta.client) return {}
    const token = readCookie('csrftoken')
    return token ? { 'x-csrftoken': decodeURIComponent(token) } : {}
  }
}
