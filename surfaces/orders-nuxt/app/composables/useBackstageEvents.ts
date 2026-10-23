import {
  openResilientEventSource,
  type ResilientEventSource,
} from "../../../operator-kit/app/utils/resilientEventSource";

// Shared same-origin SSE lifecycle for canonical backstage reads. Push invalidates;
// polling and visibility recovery use the same caller-owned coalesced refresh.
// O stream se recria sozinho, com backoff, depois do 502 de deploy; cada abertura
// (a primeira e as reaberturas) refaz o fetch canônico para cobrir o que passou.
export function useBackstageEvents(
  channel: "orders" | "catalog",
  onPush: () => void,
  opts?: { pollMs?: number; orderRef?: string },
) {
  const config = useRuntimeConfig();
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: ResilientEventSource | null = null;

  function connectSse() {
    if (source) return;
    realtime.value = "connecting";
    const onEvent = (ev: MessageEvent) => {
      // The orders channel carries every order; only refetch for this ref.
      try {
        const payload = JSON.parse(String(ev.data || "{}"));
        if (!opts?.orderRef || !payload.ref || payload.ref === opts.orderRef)
          onPush();
      } catch {
        onPush(); // unparseable push → refetch is cheap and safe
      }
    };
    source = openResilientEventSource({
      url: ssePath(`/sse/${channel}`, config.app.baseURL),
      events: [`backstage-${channel}-update`],
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
