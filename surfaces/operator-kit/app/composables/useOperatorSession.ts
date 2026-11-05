import { readonly } from "vue";

import { isUnauthenticatedError } from "../utils/httpError";

/**
 * Sessão do operador: re-gate global em 401 (omotenashi de resiliência).
 *
 * A sessão do operador pode expirar no meio do turno (cookie `.<zona>` revogado,
 * timeout do lado do Django). Sem isto, cada gravação (save_tab, close_sale…) falharia
 * silenciosamente com um toast genérico e o operador seguiria batendo numa sessão morta.
 * O transporte de comandos chama `flagIfUnauthenticated(err)` no catch; a shell observa
 * `expired` e sobe a tela de login. Estado compartilhado via `useState` (SSR-safe, um por
 * app) — o interceptor herdado pelos 4 apps de operador ([[project_operator_apps_crosssubdomain_auth_gap]]).
 */
export function useOperatorSession() {
  const expired = useState("operator-session-expired", () => false);
  // "Terminou" só existe para o que COMEÇOU. Num dispositivo cru (primeira visita,
  // sem cookie), o primeiro fetch protegido também volta 401, e a tela dizia "Sua
  // sessão terminou. Seu rascunho... foram preservados." para quem nunca entrou e
  // não tinha rascunho nenhum (beta 05/11, CMP-11). A antessala marca aqui quando
  // viu alguém identificado nesta carga do app; antes disso, 401 é só "entre".
  const hadSession = useState("operator-session-had-session", () => false);

  /**
   * Se o erro for autenticação perdida (401), devolve true (o chamador ainda pode
   * re-lançar para o tratamento de erro existente) e, se havia sessão nesta carga do
   * app, marca a sessão como expirada. 403 e demais status não disparam re-gate:
   * devolve false.
   */
  function flagIfUnauthenticated(error: unknown): boolean {
    if (isUnauthenticatedError(error)) {
      if (hadSession.value) expired.value = true;
      return true;
    }
    return false;
  }

  /** A antessala viu alguém identificado: daqui em diante, 401 é sessão que terminou. */
  function markAuthenticated() {
    hadSession.value = true;
  }

  /** Limpa o sinal após re-autenticar (login/desbloqueio bem-sucedido). */
  function reset() {
    expired.value = false;
  }

  return {
    expired: readonly(expired),
    hadSession: readonly(hadSession),
    flagIfUnauthenticated,
    markAuthenticated,
    reset,
  };
}
