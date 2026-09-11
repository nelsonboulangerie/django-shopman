// Shared same-origin SSE lifecycle for canonical backstage reads. Push invalidates;
// polling and visibility recovery use the same caller-owned coalesced refresh.
export function useBackstageEvents(channel: "orders" | "catalog", onPush: () => void, opts?: { pollMs?: number; orderRef?: string }) {
  const config = useRuntimeConfig();
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: EventSource | null = null;

  function connectSse() {
    if (source) return;
    const url = ssePath(`/sse/${channel}`, config.app.baseURL);
    try {
      realtime.value = "connecting";
      source = new EventSource(url, { withCredentials: true });
      const onEvent = (ev: MessageEvent) => {
        // The orders channel carries every order; only refetch for this ref.
        try {
          const payload = JSON.parse(String(ev.data || "{}"));
          if (!opts?.orderRef || !payload.ref || payload.ref === opts.orderRef) onPush();
        } catch {
          onPush(); // unparseable push → refetch is cheap and safe
        }
      };
      ["message", `backstage-${channel}-update`].forEach((name) => source!.addEventListener(name, onEvent));
      source.onopen = () => { realtime.value = "live"; onPush(); };
      source.onerror = () => { realtime.value = "polling"; };
    } catch {
      source = null;
      realtime.value = "polling";
    }
  }

  const onVisible = () => { if (document.visibilityState === "visible") onPush(); };
  onMounted(() => {
    pollTimer = setInterval(onPush, opts?.pollMs ?? 30_000);
    connectSse();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (source) { source.close(); source = null; }
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  return { realtime };
}
