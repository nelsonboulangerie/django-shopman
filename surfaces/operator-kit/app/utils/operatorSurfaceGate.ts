import type { OperatorSessionState } from "../presentation/operatorSessionState";

export interface OperatorSurfaceGateInput {
  /** Estado da sessão do operador (ver operatorSessionState). */
  sessionState: OperatorSessionState | string;
  /** A antessala respondeu: este dispositivo pode pedir identificação. */
  canIdentify: boolean;
  /** Erro de rede ao ler a sessão (NÃO é sessão morta). */
  sessionUnavailable: boolean;
  /** Cadeado do servidor ou da estação. */
  locked: boolean;
  /** PIN temporário: exige troca antes de operar. */
  mustChange: boolean;
  /** Harness hermético da matriz visual: só existe fora de produção. */
  harness: boolean;
}

export interface OperatorSurfaceGate {
  showPage: boolean;
  showForbidden: boolean;
  showChecking: boolean;
  showUnavailable: boolean;
  showLogin: boolean;
  showLock: boolean;
}

/**
 * Decide o que a casca de um app de operador mostra em cada estado. Uma única
 * fonte evita dois enganos já vistos: renderizar a página para quem não tem
 * permissão (canIdentify sozinho não é autorização) e empilhar a tela de senha
 * sobre o esqueleto de "conferindo acesso". Puro e testável; a casca só liga os
 * booleanos aos componentes oficiais.
 */
export function operatorSurfaceGate(input: OperatorSurfaceGateInput): OperatorSurfaceGate {
  const { sessionState, canIdentify, sessionUnavailable, locked, mustChange, harness } = input;
  const checking = sessionState === "checking";
  const expired = sessionState === "expired";
  return {
    // Defesa em profundidade: mesmo que um chamador combine estado e cadeado de
    // forma incoerente, a página nunca renderiza atrás de um cadeado.
    showPage: harness || (sessionState === "authenticated" && !locked && !mustChange),
    showForbidden: !harness && sessionState === "forbidden",
    showChecking: !harness && checking && !canIdentify,
    showUnavailable: !harness && sessionUnavailable,
    showLogin: !harness && !sessionUnavailable && !canIdentify && !checking,
    showLock: !harness && !sessionUnavailable && canIdentify && (locked || mustChange || expired),
  };
}
