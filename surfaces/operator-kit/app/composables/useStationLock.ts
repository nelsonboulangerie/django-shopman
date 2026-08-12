import { isStationLockedError } from "../utils/httpError";

/**
 * O cadeado visto pelo SERVIDOR — estado puro, sem I/O.
 *
 * A tela deriva `locked` da sessão do operador, que só é relida em poll ou ação.
 * Entre o instante em que o servidor tranca a estação e o instante em que o
 * cliente descobre, tudo continua montado enquanto cada leitura volta 403: no PDV
 * isso desenhava um quadro de comandas VAZIO, que no balcão se lê como "as
 * comandas sumiram". Um 403 `station_locked` é a informação mais nova que existe
 * sobre o cadeado, e levanta esta bandeira na hora.
 *
 * Vive separado do `useOperatorLock` porque é só estado: o transporte de comandos
 * e a leitura da Projection precisam ERGUER a bandeira sem arrastar junto o fetch
 * da sessão. Quem compõe as duas coisas é o `useOperatorLock`.
 */
export function useStationLock() {
  const denied = useState("operator-lock-denied", () => false);

  /** Marca a estação travada se o erro for a recusa do servidor. */
  function flagIfStationLocked(error: unknown): boolean {
    if (!isStationLockedError(error)) return false;
    denied.value = true;
    return true;
  }

  /** Abaixa a bandeira (desbloqueio bem-sucedido). */
  function clear(): void {
    denied.value = false;
  }

  return { denied, flagIfStationLocked, clear };
}
