import { readonly } from "vue";

import type { OperatorSession } from "../types/operator";
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
/**
 * Marca, nesta ABA, que alguém entrou (`sessionStorage`: morre com a aba, não passa
 * para outra). O `hadSession` acima vive só nesta carga do app, e o login recarrega a
 * página: a sessão que caía logo depois de entrar voltava ao login vazio, "Entre para
 * operar o caixa", como se ninguém tivesse entrado (P2-15 do plano de excelência do
 * PDV, #3194). Com a marca, o login seguinte sabe que a sessão terminou e diz isso.
 */
export const SIGNED_IN_HERE_KEY = "shopman:operator-signed-in-here";

function storage(): Storage | null {
  if (!import.meta.client) return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

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
      if (hadSession.value || sessionShowedSomeone()) expired.value = true;
      return true;
    }
    return false;
  }

  // A antessala lida nesta carga (`operator-session`) já mostrou alguém: isso É ter
  // tido sessão, em qualquer app. A Central lê a antessala sem `useOperatorLock`, e
  // sem esta leitura nunca marcava `hadSession`: a sessão que morria no meio do
  // turno deixava de dizer "Sua sessão expirou".
  function sessionShowedSomeone(): boolean {
    return Boolean(useNuxtData<OperatorSession>("operator-session").data.value?.operator);
  }

  /** A antessala viu alguém identificado: daqui em diante, 401 é sessão que terminou. */
  function markAuthenticated() {
    hadSession.value = true;
    rememberSignedIn();
  }

  /** Entrou nesta aba: o login seguinte, se a sessão cair, diz que ela terminou. */
  function rememberSignedIn() {
    try {
      storage()?.setItem(SIGNED_IN_HERE_KEY, "1");
    } catch {
      // Armazenamento recusado (modo privado, cota): o login só perde o motivo.
    }
  }

  /** Saiu de propósito: o próximo login é um começo, não uma sessão que caiu. */
  function forgetSignedIn() {
    try {
      storage()?.removeItem(SIGNED_IN_HERE_KEY);
    } catch {
      // Idem: sem armazenamento não há marca a apagar.
    }
  }

  /**
   * Alguém entrou nesta aba antes desta tela de login? Só no cliente (o servidor não
   * vê a aba): quem desenha o login lê isto ao montar, não no SSR.
   */
  function signedInHereBefore(): boolean {
    try {
      return storage()?.getItem(SIGNED_IN_HERE_KEY) === "1";
    } catch {
      return false;
    }
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
    rememberSignedIn,
    forgetSignedIn,
    signedInHereBefore,
    reset,
  };
}
