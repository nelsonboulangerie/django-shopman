/**
 * O aviso de página da loja (#3242): uma frase que um gesto deixa para a página seguinte
 * ler, como "Pronto, sua conta foi excluída." depois de excluir a conta.
 *
 * Mora abaixo das barras do topo, como primeiro conteúdo da página, com fundo sólido e X
 * (`components/PageNotice.vue`, no shell). Não é toast: o toast flutua por cima do
 * conteúdo e some sozinho, e o que o aviso diz é o fim de um gesto, para ser lido.
 *
 * `path` é a página em que ele aparece; sair dela o tira.
 *
 * Opcionais (#3267): `action` é o botão que resolve o que o aviso diz (todo aviso traz a
 * saída, nunca o caminho escrito); `tone` separa o fim de um gesto que deu certo
 * (`success`, o padrão) do aviso que pede atenção (`attention`), para o ícone não dizer
 * "deu certo" sobre uma recusa.
 */
export interface PageNoticeAction {
  label: string
  to: string
}

export type PageNoticeTone = 'success' | 'attention'

export interface PageNotice {
  message: string
  path: string
  action?: PageNoticeAction
  tone?: PageNoticeTone
}

export interface PageNoticeOptions {
  action?: PageNoticeAction
  tone?: PageNoticeTone
}

export function usePageNotice () {
  const notice = useState<PageNotice | null>('storefront-page-notice', () => null)

  function show (message: string, path: string, options: PageNoticeOptions = {}) {
    notice.value = {
      message,
      path,
      ...(options.action ? { action: options.action } : {}),
      ...(options.tone ? { tone: options.tone } : {})
    }
  }

  function dismiss () {
    notice.value = null
  }

  return { notice, show, dismiss }
}
