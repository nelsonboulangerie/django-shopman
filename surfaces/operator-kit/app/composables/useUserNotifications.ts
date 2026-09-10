// Canal PESSOAL da pessoa (`user-<id>` no Django, `/sse/notifications` no BFF).
// O push só invalida; cada superfície refaz seu fetch canônico.
export function useUserNotifications(onPush: () => void) {
  const config = useRuntimeConfig();
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let source: EventSource | null = null;

  function connect() {
    if (source) return;
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
    connect();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    if (source) source.close();
    source = null;
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  return { realtime };
}
