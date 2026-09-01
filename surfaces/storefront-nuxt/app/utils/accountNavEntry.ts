// A PORTA DE ENTRADA DA LOJA, dita com o nome dela.
//
// Até aqui não existia "Entrar" em lugar nenhum: quem quisesse se identificar
// tinha que tocar em **Conta**, ser barrado pelo guard e cair no login. Três
// consequências, todas ruins:
//
//   1. O cliente que só queria entrar era levado a uma tela que não pediu.
//   2. O rótulo mentia: "Conta" prometia a conta e entregava um formulário.
//   3. O caminho tinha um salto a mais (`/conta` → guard → `/entrar`), e cada
//      salto é uma chance de o cliente achar que se perdeu.
//
// A correção não inventa espaço novo na tela: é o MESMO slot dizendo a verdade
// sobre o que acontece ao ser tocado. Deslogado ele é a porta ("Entrar", ícone
// de entrada, indo direto ao login com a página atual guardada); logado ele é a
// conta, como sempre foi.

export interface AccountNavEntry {
  to: string
  label: string
  icon: string
}

/** Rotas onde guardar "de onde vim" só produziria um laço de volta ao login. */
const ROTAS_DE_AUTENTICACAO = ['/entrar', '/a']

function ehRotaDeAutenticacao(caminho: string): boolean {
  const semQuery = (caminho || '').split('?')[0] || ''
  return ROTAS_DE_AUTENTICACAO.some(rota => semQuery === rota || semQuery.startsWith(`${rota}/`))
}

/** Só caminho interno vira `next` — `//evil.com` é redirecionamento aberto. */
function origemSegura(caminho: string | undefined | null): string {
  const valor = (caminho || '').trim()
  if (!valor.startsWith('/') || valor.startsWith('//') || valor.startsWith('/\\')) return ''
  return ehRotaDeAutenticacao(valor) ? '' : valor
}

/**
 * O item de navegação da conta, conforme quem está olhando.
 *
 * ``rotuloLogado`` existe porque os três lugares que consomem isto falam em
 * larguras diferentes: a barra de baixo cabe "Conta", o menu do cabeçalho cabe
 * "Conta e pedidos". O rótulo DESLOGADO é sempre "Entrar" — a porta tem um nome
 * só, e ele não muda conforme o espaço disponível.
 *
 * Deslogado, o destino já leva `?next=` com a página atual: o cliente volta para
 * onde estava, e o guard nem precisa entrar em ação (ele continua valendo para
 * quem chega por link direto em rota protegida).
 */
export function accountNavEntry(
  isAuthenticated: boolean,
  currentPath: string,
  rotuloLogado = 'Conta',
): AccountNavEntry {
  if (isAuthenticated) {
    return { to: '/conta', label: rotuloLogado, icon: 'lucide:user-round' }
  }
  const origem = origemSegura(currentPath)
  return {
    to: origem ? `/entrar?next=${encodeURIComponent(origem)}` : '/entrar',
    label: 'Entrar',
    icon: 'lucide:log-in',
  }
}
