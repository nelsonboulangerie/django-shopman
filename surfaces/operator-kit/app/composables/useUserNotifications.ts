import {
  openResilientEventSource,
  type ResilientEventSource,
} from "../utils/resilientEventSource";

// Canal PESSOAL da pessoa (`user-<id>` no Django, `/sse/notifications` no BFF).
// O push só invalida; cada superfície refaz seu fetch canônico. O stream se
// recria sozinho, com backoff, depois do 502 de deploy, e ao reabrir refaz o
// fetch: a notificação que nasceu com o push fora não veio por ele.
//
// Não registra ciclo de vida: quem decide quando o stream existe é a caixa
// compartilhada (`useNotifications`, via `useSharedLive`), que o liga quando o
// primeiro sino monta e o desliga quando o último desmonta. Um stream por app.
export function useUserNotifications(onPush: () => void) {
  const config = useRuntimeConfig();
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let source: ResilientEventSource | null = null;
  let running = false;
  const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  const owner = () => session.value?.operator?.id;
  watch(owner, () => {
    source?.close();
    source = null;
    realtime.value = "polling";
    if (running) connect();
  }, { flush: "sync" });

  function connect() {
    if (source || owner() == null) return;
    realtime.value = "connecting";
    source = openResilientEventSource({
      url: ssePath("/sse/notifications", config.app.baseURL),
      events: ["user-notification"],
      onEvent: () => onPush(),
      onOpen: (reconnected) => {
        realtime.value = "live";
        if (reconnected) onPush();
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

  /** Abre o stream e devolve como fechá-lo. */
  function start(): () => void {
    running = true;
    connect();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    return () => {
      running = false;
      source?.close();
      source = null;
      realtime.value = "polling";
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
    };
  }

  return { realtime, start };
}
