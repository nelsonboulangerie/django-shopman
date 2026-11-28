// Uma coisa viva por app, e não uma por componente que a usa.
//
// O sino mora no cabeçalho, na barra lateral, na barra compacta e no shell; a atenção
// dos canais do Gestor, no app.vue, na fila e no sinal da fila. Cada um abria o próprio
// SSE e o próprio poll: na fila do Gestor eram mais de cinco conexões longas na mesma
// origem, e em HTTP/1.1 (dev, servidor local da contingência) o teto de seis por host
// enfileirava o resto, até o POST de travar a tela (beta 05/11, GES-01 e PDV2-02).
//
// `useSharedLive(key, setup, live)`:
// - `setup` roda UMA vez por app (o estado e as funções ficam compartilhados);
// - `live` liga o que custa conexão (SSE, poll) quando o PRIMEIRO componente monta e
//   devolve como desligar, chamado quando o ÚLTIMO desmonta.
//
// O registro mora no `nuxtApp`, e não no módulo: no servidor cada requisição tem o seu
// e nada vaza entre pessoas. O `setup` roda num escopo destacado, para que o primeiro
// componente desmontar não leve junto os `watch` de quem continua montado.
import { effectScope } from "vue";

interface SharedEntry {
  api: unknown;
  subscribers: number;
  stop: (() => void) | null;
}

type SharedHost = { _operatorSharedLive?: Map<string, SharedEntry> };

function registry(): Map<string, SharedEntry> {
  const host = useNuxtApp() as unknown as SharedHost;
  host._operatorSharedLive ??= new Map();
  return host._operatorSharedLive;
}

export function useSharedLive<T>(
  key: string,
  setup: () => T,
  live: (api: T) => () => void,
): T {
  const shared = registry();
  let entry = shared.get(key);
  if (!entry) {
    const scope = effectScope(true);
    entry = { api: scope.run(setup), subscribers: 0, stop: null };
    shared.set(key, entry);
  }
  const current = entry;
  onMounted(() => {
    current.subscribers += 1;
    if (current.subscribers === 1) current.stop = live(current.api as T);
  });
  onBeforeUnmount(() => {
    current.subscribers = Math.max(0, current.subscribers - 1);
    if (current.subscribers > 0) return;
    current.stop?.();
    current.stop = null;
  });
  return current.api as T;
}
