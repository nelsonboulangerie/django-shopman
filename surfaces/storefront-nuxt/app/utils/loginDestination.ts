// PARA ONDE O CLIENTE VOLTA DEPOIS DE ENTRAR.
//
// A regra da casa é curta: **preservar onde ele estava ou queria ir, ou a home
// como último recurso.** Nunca despejar numa tela que ele não pediu.
//
// ## Por que isso quebrava justamente na aba "Conta"
//
// Não existe botão "Entrar" na loja. A única porta é a aba **Conta** — e o
// guard de rota grava como destino a rota que o cliente tentou abrir. Resultado:
// quem tocava em "Conta" só para se identificar era mandado de volta para
// `/conta` depois do login, uma tela que ele nunca pediu, perdendo a página em
// que estava.
//
// "Entrar" e "ver minha conta" viraram o MESMO gesto por construção, e por isso
// o destino sempre era a conta.
//
// ## A distinção que resolve
//
// - `/conta` **puro** é a porta de login, não um destino. Quem passa por ela
//   volta para onde estava.
// - `/conta/pedidos`, `/conta/perfil`, `/finalizar`, `/pedido/X` são pedidos
//   EXPLÍCITOS: o cliente disse o que queria ver, e isso se preserva.
//
// A diferença é entre "me identifica" e "me leva ali".

import { safeInternalPath } from './safeNavigation'

/** A porta de login disfarçada de destino. */
const CONTA_RAIZ = '/conta'

/** Rotas que nunca são destino de volta: voltar para o login é um laço. */
const ROTAS_DE_AUTENTICACAO = ['/entrar', '/a']

function ehRotaDeAutenticacao(caminho: string): boolean {
  const semQuery = caminho.split('?')[0] || ''
  return ROTAS_DE_AUTENTICACAO.some(rota => semQuery === rota || semQuery.startsWith(`${rota}/`))
}

/**
 * O destino a gravar no `?next=` quando o guard barra uma rota autenticada.
 *
 * `destino` é a rota que o cliente tentou abrir; `origem` é de onde ele veio
 * (vazia numa entrada direta — link, favorito, digitação).
 *
 * ⚠️ Entrada DIRETA em `/conta` preserva `/conta`. Quem digitou o endereço ou
 * abriu um favorito realmente queria a conta — mandá-lo para a home seria trocar
 * um destino errado por outro. A regra só desarma o `/conta` que funcionou como
 * botão de login, e a prova disso é ter havido uma página ANTES.
 */
export function loginDestination(destino: string, origem?: string | null): string {
  const alvo = safeInternalPath(destino)
  const veio = origem ? safeInternalPath(origem, '') : ''

  const soQueriaEntrar =
    alvo.split('?')[0] === CONTA_RAIZ
    && Boolean(veio)
    && veio !== alvo
    && !ehRotaDeAutenticacao(veio)

  return soQueriaEntrar ? veio : alvo
}
