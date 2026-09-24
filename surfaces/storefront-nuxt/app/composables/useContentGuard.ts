// PÁGINA INDEXÁVEL NÃO RESPONDE 200 QUANDO A BUSCA FALHOU.
//
// A loja é SSR: se a API não responde, o `useFetch` devolve erro e a página
// renderiza a casca — cabeçalho, rodapé, título genérico — com status 200. Para
// quem visita é uma tela vazia; para o Google é uma página boa, e as 42 páginas
// de produto viram 42 páginas iguais, com o mesmo `<title>Produto</title>` e a
// mesma descrição. Medido no ar em 23/09/2026: durante o 504 do `api.` (reinício
// de deploy) toda PDP respondia 200 sem nome de produto, e no mesmo dia o Search
// Console acusou "Cópia, o Google e o usuário selecionaram uma página canônica
// diferente" — é o que ele faz ao achar muitas páginas iguais: escolhe uma e
// descarta as outras.
//
// 503 é a resposta certa: "não guarde isto, volte depois". O `Retry-After` diz
// quanto depois. A tela é a mesma de sempre (`error.vue`, com "Tente de novo").
//
// ⚠️ A régua é a FALHA da busca, não o vazio. Backend que responde 200 sem dado
// continua caindo na casca digna do WP-S5 (`tests/e2e/resilience.spec.ts`):
// vitrine vazia é estado possível da casa; backend mudo não é.
//
// ⚠️ Só no SERVIDOR. No cliente a página já está montada, e o caminho é o "Tente
// de novo" inline — derrubar a tela de quem já está navegando seria pior.
export function shouldFailOnSsr (
  isServer: boolean,
  failure: { statusCode?: number } | null | undefined,
  hasContent: boolean
): boolean {
  return isServer && !!failure && !hasContent
}

export function requireContentOnSsr (
  failure: { statusCode?: number } | null | undefined,
  hasContent: boolean,
  subject: string
): void {
  if (!shouldFailOnSsr(import.meta.server, failure, hasContent)) return
  const event = useRequestEvent()
  if (event) event.node.res.setHeader('retry-after', '120')
  throw createError({
    statusCode: 503,
    statusMessage: `${subject} indisponível no momento`,
    fatal: true
  })
}
