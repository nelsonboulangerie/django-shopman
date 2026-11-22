/**
 * O aviso de página da loja (#3242): uma frase que um gesto deixa para a página seguinte
 * ler, como "Pronto, sua conta foi excluída." depois de excluir a conta.
 *
 * Mora abaixo das barras do topo, como primeiro conteúdo da página, com fundo sólido e X
 * (`components/PageNotice.vue`, no shell). Não é toast: o toast flutua por cima do
 * conteúdo e some sozinho, e o que o aviso diz é o fim de um gesto, para ser lido.
 *
 * `path` é a página em que ele aparece; sair dela o tira.
 */
export interface PageNotice {
  message: string
  path: string
}

export function usePageNotice () {
  const notice = useState<PageNotice | null>('storefront-page-notice', () => null)

  function show (message: string, path: string) {
    notice.value = { message, path }
  }

  function dismiss () {
    notice.value = null
  }

  return { notice, show, dismiss }
}
