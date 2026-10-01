// Decisões PURAS da troca de versão do app instalado da loja: sem DOM, sem timer,
// sem rede. Quem as executa é `usePwaUpdateCheck` e `PwaUpdatePrompt`; quem as prova
// é `tests/pwaRuntime.test.ts`.
//
// Porte do `operator-kit/app/presentation/pwaRuntime.ts` (17/09/2026, commit
// 976152c7b). O problema é o mesmo: com `registerType: 'prompt'` o worker novo fica
// em "waiting" até TODAS as janelas do host fecharem, e o app instalado que fica dias
// aberto nunca fecha todas.
//
// Decisão do dono (D9, 01/10/2026): a loja FORÇA a versão nova. Duas portas, as duas
// fechadas nas telas protegidas (`pwaUpdateRouteProtected`):
//   1. Navegação entre telas vira recarga completa no destino
//      (`shouldApplyPwaUpdateOnNavigation`).
//   2. Fora das telas protegidas, um aviso que bloqueia a tela até o toque em
//      "Atualizar" (`shouldBlockForPwaUpdate`).
// A metade "aplicar sozinho no ocioso" do kit continua de fora: a loja não sabe se o
// cliente está parado ou lendo, e recarrega só num gesto dele (navegar ou tocar).

/** Sonda a cada 30 min: pega o deploy do dia sem transformar a loja em pinger. */
export const PWA_UPDATE_CHECK_MS = 30 * 60 * 1000

/** Piso entre sondas: foco/visibilidade/rede disparam em rajada ao voltar do sono. */
export const PWA_UPDATE_CHECK_FLOOR_MS = 60 * 1000

/**
 * Sondar agora? Vale para os gatilhos OPORTUNISTAS (voltar à vista, ganhar foco), que
 * chegam em rajada quando o aparelho acorda e precisam de um piso entre si. A sonda
 * do intervalo de 30 min e a da volta da rede não passam por aqui.
 */
export function shouldCheckForUpdate (options: {
  now: number
  lastCheckAt: number
  online: boolean
  visible: boolean
  floorMs?: number
}): boolean {
  if (!options.online || !options.visible) return false
  const floor = options.floorMs ?? PWA_UPDATE_CHECK_FLOOR_MS
  // Relógio para trás (hora do aparelho ajustada) não pode congelar a sonda.
  if (options.now < options.lastCheckAt) return true
  return options.now - options.lastCheckAt >= floor
}

/**
 * Telas PROTEGIDAS: aqui a versão nova nunca entra, nem por recarga na navegação nem
 * por aviso que bloqueia. A exceção é deliberada (D9): o cliente pode estar digitando
 * endereço, escolhendo o pagamento ou pagando (checkout e pedido, onde mora o Pix e o
 * cartão), ou digitando o código de acesso (login e o link de acesso `/a`). Recarregar
 * ali perde o que está em curso, e no pagamento isso custa mais que alguns minutos na
 * versão velha. A versão nova entra na primeira tela seguinte
 * que não estiver nesta lista.
 */
export function pwaUpdateRouteProtected (path: string): boolean {
  if (path === '/finalizar' || path.startsWith('/finalizar/')) return true
  if (path.startsWith('/pedido/')) return true
  return path === '/entrar' || path === '/a'
}

export interface PwaUpdateBlockState {
  /** Há worker novo em "waiting". */
  needsRefresh: boolean
  /** Sem rede, a página recarregada cairia no casco offline: espera a conexão voltar. */
  online: boolean
  path: string
}

/** Bloquear a tela? Sempre que houver versão nova, rede e a tela não for protegida. */
export function shouldBlockForPwaUpdate (state: PwaUpdateBlockState): boolean {
  return state.needsRefresh && state.online && !pwaUpdateRouteProtected(state.path)
}

export interface PwaUpdateNavigationState {
  needsRefresh: boolean
  online: boolean
  /** Caminho de onde o cliente saiu. */
  from: string
  /** Caminho aonde ele chegou: é ali que a página recarrega. */
  to: string
}

/**
 * A navegação vira recarga completa no destino? Só com versão nova e rede, e só
 * quando NENHUMA das duas pontas é protegida: sair do checkout para o menu não
 * recarrega (quem acabou de pagar volta ao menu e encontra o aviso), e entrar no
 * checkout também não (o cliente chega ao pagamento sem uma tela piscando).
 */
export function shouldApplyPwaUpdateOnNavigation (state: PwaUpdateNavigationState): boolean {
  if (!state.needsRefresh || !state.online) return false
  if (state.from === state.to) return false
  return !pwaUpdateRouteProtected(state.from) && !pwaUpdateRouteProtected(state.to)
}
