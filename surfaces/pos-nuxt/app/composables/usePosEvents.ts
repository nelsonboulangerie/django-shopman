import { shouldPollTick, type PosRealtimeState } from "~/presentation/events";

/**
 * Tempo real entre estações do PDV: SSE push + poll de fallback + wake.
 *
 * EventSource same-origin no BFF (/sse/cash → proxy do eventstream do Django,
 * canal `backstage-cash-main`). O canal anuncia o que OUTRA estação fez e esta
 * precisa ver sem F5: pedido de troco (pedido/atendido/cancelado), devolução
 * pendente/entregue, turno aberto/fechado. Todo evento dispara o MESMO
 * `onPush` — o refetch da Projection do terminal, que é o fetch canônico onde
 * pendências, turno e comandas já vivem (ADR-016: o push é sinal, o fetch é a
 * verdade).
 *
 * Fallback: poll calmo (60s) só enquanto o SSE não está vivo — se o stream
 * conecta, o tick não refaz nada. Tablet que dormiu/voltou à aba refaz na hora
 * e tenta reconectar o stream (um 403 na conexão fecha o EventSource de vez;
 * sem esta retomada, a estação ficaria no poll para sempre).
 */
export function usePosEvents(onPush: () => void, opts?: { pollMs?: number }) {
  const config = useRuntimeConfig();
  const realtime = ref<PosRealtimeState>("polling");
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: EventSource | null = null;

  function connectSse() {
    if (source) return;
    const url = ssePath("/sse/cash", config.app.baseURL);
    try {
      realtime.value = "connecting";
      source = new EventSource(url, { withCredentials: true });
      // django-eventstream empurra eventos nomeados; qualquer um = refetch.
      const onEvent = () => onPush();
      ["message", "backstage-cash-update"].forEach((name) => source!.addEventListener(name, onEvent));
      source.onopen = () => { realtime.value = "live"; };
      source.onerror = () => { realtime.value = "polling"; };
    } catch {
      source = null;
      realtime.value = "polling";
    }
  }

  const onVisible = () => {
    if (document.visibilityState !== "visible") return;
    onPush();
    // Stream fechado de vez (ex.: conexão recusada antes do login)? Tenta de
    // novo — a sessão pode ter nascido desde então.
    if (source && source.readyState === EventSource.CLOSED) {
      source.close();
      source = null;
    }
    connectSse();
  };

  onMounted(() => {
    pollTimer = setInterval(() => {
      if (shouldPollTick(realtime.value)) onPush();
    }, opts?.pollMs ?? 60_000);
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
