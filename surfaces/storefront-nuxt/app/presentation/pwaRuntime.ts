// Decisões PURAS da troca de versão do app instalado da loja: sem DOM, sem timer,
// sem rede. Quem as executa é `usePwaUpdateCheck` e `PwaUpdatePrompt`; quem as prova
// é `tests/pwaRuntime.test.ts`.
//
// Porte do `operator-kit/app/presentation/pwaRuntime.ts` (17/09/2026, commit
// 976152c7b). O problema é o mesmo: com `registerType: 'prompt'` o worker novo fica
// em "waiting" até TODAS as janelas do host fecharem, e o app instalado que fica dias
// aberto nunca fecha todas. No PDV isso deixou o desktop do dono dias no bundle
// antigo; na loja, o cliente instalado ficava preso numa versão velha com um único
// toast descartável como saída.
//
// O kit tem duas metades: SONDAR e APLICAR sozinho quando a superfície prova que é
// seguro. A loja porta só a primeira. Aplicar sozinho significa recarregar a página
// do cliente sem ele pedir, e o cliente pode estar escolhendo endereço, digitando o
// código de acesso ou pagando: ninguém publica "estou no meio de algo" em todas essas
// telas. Na loja quem aplica é sempre o toque do cliente no aviso.

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
 * Telas em que o aviso NÃO aparece, porque o toque nele recarrega a página e ali há
 * algo em curso que a recarga perderia: o checkout, o pedido (onde mora o pagamento)
 * e o login (código de acesso sendo digitado). O aviso não some para sempre: volta
 * na próxima tela que não estiver nesta lista.
 */
export function pwaUpdatePromptRouteExcluded (path: string): boolean {
  if (path === '/finalizar' || path.startsWith('/finalizar/')) return true
  if (path.startsWith('/pedido/')) return true
  return path === '/entrar' || path === '/a'
}

export interface PwaUpdatePromptState {
  /** Há worker novo em "waiting". */
  needsRefresh: boolean
  /** Sem rede, a página recarregada cairia no casco offline: espera a conexão voltar. */
  online: boolean
  path: string
}

/** O aviso é persistente: aparece SEMPRE que houver versão nova e a tela permitir. */
export function shouldShowPwaUpdatePrompt (state: PwaUpdatePromptState): boolean {
  return state.needsRefresh && state.online && !pwaUpdatePromptRouteExcluded(state.path)
}
