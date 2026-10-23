/**
 * Quanto o PDV espera uma resposta. Sem prazo, um link caído com o wi-fi de pé
 * pendurava a chamada até o TCP desistir (minutos), com o cliente na frente.
 * Os dois prazos ficam um pouco acima do prazo do BFF (`DJANGO_UPSTREAM_TIMEOUT_MS`,
 * 25 s) no fechamento, para que o "não respondeu" chegue com o código do BFF.
 */
export const POS_REQUEST_TIMEOUT_MS = 15_000;
export const POS_CLOSE_SALE_TIMEOUT_MS = 30_000;

export function usePosAction() {
  const apiPath = useApiPath();
  // Toda resposta (ou falta dela) diz se o servidor está ao alcance: é o que faz
  // o PDV entrar no modo sem conexão com o wi-fi de pé e o link caído.
  const reachability = useReachability();
  // Re-gate global em 401: toda mutação passa por aqui, então uma sessão de
  // dispositivo expirada é detectada num único ponto e sobe a tela de login
  // (em vez de o operador seguir batendo numa sessão morta).
  const session = useOperatorSession();
  // Re-gate irmão em 403 `station_locked`: o cadeado do servidor tem a palavra
  // final sobre o cadeado da tela, senão o operador insiste num comando que
  // nunca vai passar e só vê um toast genérico. Estado puro — o transporte de
  // comandos não carrega o fetch da sessão junto.
  const { flagIfStationLocked } = useStationLock();

  function csrfHeader(): Record<string, string> {
    const token = useCookie("csrftoken").value || "";
    return token ? { "X-CSRFToken": token } : {};
  }

  async function call<T = unknown>(
    path: string,
    options: {
      method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
      body?: Record<string, unknown>;
      /** Prazo da chamada; padrão `POS_REQUEST_TIMEOUT_MS`. */
      timeoutMs?: number;
    } = {},
  ): Promise<T> {
    try {
      // Sem o mapa de rotas tipadas do Nitro: com uma rota literal no server
      // (/sse/cash), o matcher de tipos do `$fetch` tenta casar `string` contra
      // cada rota e explode ("excessive stack depth"). O caminho aqui é
      // dinâmico (vem da Projection), então o contrato de tipo sempre foi do
      // chamador — o cast só torna isso dito.
      const request = $fetch as (url: string, opts?: {
        method?: string;
        credentials?: RequestCredentials;
        headers?: Record<string, string>;
        body?: unknown;
        signal?: AbortSignal;
      }) => Promise<unknown>;
      const answer = (await request(apiPath(path), {
        method: options.method || "POST",
        credentials: "include",
        headers: csrfHeader(),
        body: options.body,
        signal: timeoutSignal(options.timeoutMs ?? POS_REQUEST_TIMEOUT_MS),
      })) as T;
      reachability.noteSuccess();
      return answer;
    } catch (error) {
      reachability.noteFailure(error);
      // 401 → marca a sessão expirada; re-lança para o tratamento de erro do
      // chamador (serverError/toast) seguir funcionando como sinal secundário.
      session.flagIfUnauthenticated(error);
      flagIfStationLocked(error);
      throw error;
    }
  }

  return { call };
}
