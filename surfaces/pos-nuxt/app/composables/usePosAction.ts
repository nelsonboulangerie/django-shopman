export function usePosAction() {
  const apiPath = usePosApiPath();
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
    options: { method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"; body?: Record<string, unknown> } = {},
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
      }) => Promise<unknown>;
      return (await request(apiPath(path), {
        method: options.method || "POST",
        credentials: "include",
        headers: csrfHeader(),
        body: options.body,
      })) as T;
    } catch (error) {
      // 401 → marca a sessão expirada; re-lança para o tratamento de erro do
      // chamador (serverError/toast) seguir funcionando como sinal secundário.
      session.flagIfUnauthenticated(error);
      flagIfStationLocked(error);
      throw error;
    }
  }

  return { call };
}
