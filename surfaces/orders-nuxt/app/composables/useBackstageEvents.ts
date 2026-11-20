import {
  subscribeSharedEventSource,
  type SharedEventSourceSubscription,
} from "../../../operator-kit/app/utils/sharedEventSource";

// Shared same-origin SSE lifecycle for canonical backstage reads. Push invalidates;
// polling and visibility recovery use the same caller-owned coalesced refresh.
// O stream se recria sozinho, com backoff, depois do 502 de deploy; cada abertura
// (a primeira e as reaberturas) refaz o fetch canônico para cobrir o que passou.
// Um stream por canal na aba (`subscribeSharedEventSource`): cada chamada assina o
// mesmo `/sse/<canal>`, em vez de abrir o seu (beta 05/11, GES-01).
//
// O canal de pedidos leva também a posição do entregador (`backstage-courier-position`,
// F7b). Toda assinatura do canal escuta os dois eventos, para continuar UM stream só
// (a chave do stream compartilhado inclui a lista de eventos); só quem passa
// `onCourierPosition` reage à posição. O resto da tela não refaz o fetch a cada 10 s.
const CHANNEL_EVENTS = {
  orders: ["backstage-orders-update", "backstage-courier-position"],
  catalog: ["backstage-catalog-update"],
} as const;
const COURIER_POSITION_EVENT = "backstage-courier-position";

export function useBackstageEvents(
  channel: "orders" | "catalog",
  onPush: () => void,
  opts?: { pollMs?: number; orderRef?: string; onCourierPosition?: () => void },
) {
  const config = useRuntimeConfig();
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: SharedEventSourceSubscription | null = null;

  function connectSse() {
    if (source) return;
    realtime.value = "connecting";
    const onEvent = (ev: MessageEvent) => {
      if (ev.type === COURIER_POSITION_EVENT) {
        opts?.onCourierPosition?.();
        return;
      }
      // The orders channel carries every order; only refetch for this ref.
      try {
        const payload = JSON.parse(String(ev.data || "{}"));
        if (!opts?.orderRef || !payload.ref || payload.ref === opts.orderRef)
          onPush();
      } catch {
        onPush(); // unparseable push → refetch is cheap and safe
      }
    };
    source = subscribeSharedEventSource({
      url: ssePath(`/sse/${channel}`, config.app.baseURL),
      events: [...CHANNEL_EVENTS[channel]],
      onEvent,
      onOpen: () => {
        realtime.value = "live";
        onPush();
      },
      onDown: () => {
        realtime.value = "polling";
      },
    });
  }

  const onVisible = () => {
    if (document.visibilityState !== "visible") return;
    onPush();
    source?.reconnectNow();
  };
  onMounted(() => {
    pollTimer = setInterval(onPush, opts?.pollMs ?? 30_000);
    connectSse();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    source?.close();
    source = null;
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  return { realtime };
}
