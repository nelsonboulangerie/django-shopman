// Canal PESSOAL da pessoa (`user-<id>` no Django, `/sse/notifications` no BFF).
// O push só invalida; cada superfície refaz seu fetch canônico.
export function useUserNotifications(onPush: () => void) {
  const config = useRuntimeConfig();
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let source: EventSource | null = null;
  let mounted = false;
  const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  const owner = () => session.value?.operator?.id;
  watch(owner, () => {
    source?.close();
    source = null;
    realtime.value = "polling";
    if (mounted) connect();
  }, { flush: "sync" });

  function connect() {
    if (source || owner() == null) return;
    const url = ssePath("/sse/notifications", config.app.baseURL);
    try {
      realtime.value = "connecting";
      source = new EventSource(url, { withCredentials: true });
      ["message", "user-notification"].forEach((name) =>
        source!.addEventListener(name, () => onPush()),
      );
      source.onopen = () => { realtime.value = "live"; };
      source.onerror = () => { realtime.value = "polling"; };
    } catch {
      source = null;
      realtime.value = "polling";
    }
  }

  const onVisible = () => {
    if (document.visibilityState === "visible") onPush();
  };

  onMounted(() => {
    mounted = true;
    connect();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    mounted = false;
    if (source) {
      source.close();
      source = null;
    }

    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  return { realtime };
}
