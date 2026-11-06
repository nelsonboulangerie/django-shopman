import {
  openResilientEventSource,
  type ResilientEventSource,
} from "./resilientEventSource";

// UM stream por canal na aba, por mais telas e peças que o escutem.
//
// O Gestor abria `/sse/catalog` no app.vue (atenção dos canais), de novo na fila, no
// sinal da fila e na página do catálogo: quatro conexões longas iguais na mesma origem
// (beta 05/11, GES-01). Em HTTP/1.1 o navegador dá seis conexões por host, e com elas
// tomadas o POST de travar a tela ficava na fila. Aqui quem assina recebe os eventos de
// um stream só; ele abre no primeiro que assina e fecha quando o último sai.
//
// Só roda no navegador: quem assina o faz ao montar. A tabela é do módulo porque o
// navegador tem um app por aba.

export interface SharedEventSourceSubscriber {
  onEvent: (event: MessageEvent) => void;
  /** Abriu (ou já estava aberto quando esta assinatura chegou: `reconnected` falso). */
  onOpen?: (reconnected: boolean) => void;
  onDown?: () => void;
}

export interface SharedEventSourceSubscription {
  /** Tenta reabrir já (volta à aba, rede voltou), para todos que escutam. */
  reconnectNow(): void;
  /** Sai da escuta; o último a sair fecha o stream. */
  close(): void;
}

interface Hub {
  source: ResilientEventSource;
  subscribers: Set<SharedEventSourceSubscriber>;
  live: boolean;
}

const hubs = new Map<string, Hub>();

export function subscribeSharedEventSource(
  options: { url: string; events: string[] } & SharedEventSourceSubscriber,
): SharedEventSourceSubscription {
  const key = `${options.url}#${[...options.events].sort().join(",")}`;
  const subscriber: SharedEventSourceSubscriber = {
    onEvent: options.onEvent,
    onOpen: options.onOpen,
    onDown: options.onDown,
  };
  let hub = hubs.get(key);
  if (!hub) {
    const subscribers = new Set<SharedEventSourceSubscriber>();
    const created: Hub = {
      subscribers,
      live: false,
      source: openResilientEventSource({
        url: options.url,
        events: options.events,
        onEvent: (event) => {
          for (const each of [...subscribers]) each.onEvent(event);
        },
        onOpen: (reconnected) => {
          created.live = true;
          for (const each of [...subscribers]) each.onOpen?.(reconnected);
        },
        onDown: () => {
          created.live = false;
          for (const each of [...subscribers]) each.onDown?.();
        },
      }),
    };
    hub = created;
    hubs.set(key, hub);
  }
  const current = hub;
  current.subscribers.add(subscriber);
  if (current.live) subscriber.onOpen?.(false);
  let closed = false;
  return {
    reconnectNow() {
      if (!closed) current.source.reconnectNow();
    },
    close() {
      if (closed) return;
      closed = true;
      current.subscribers.delete(subscriber);
      if (current.subscribers.size) return;
      current.source.close();
      if (hubs.get(key) === current) hubs.delete(key);
    },
  };
}
