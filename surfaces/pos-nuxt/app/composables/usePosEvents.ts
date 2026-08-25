import { shouldPollTick, type PosRealtimeState } from "~/presentation/events";

/**
 * Tempo real entre estações do PDV: SSE push + poll de fallback + wake.
 *
 * EventSource same-origin no BFF: /sse/cash (canal `backstage-cash-main`) e
 * /sse/tabs (canal `backstage-tabs-main`, a cozinha mexendo numa comanda). O canal anuncia o que OUTRA estação fez e esta
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
  let sources: EventSource[] = [];

  /** Os canais que o balcão assina, e o evento nomeado de cada um. Dois streams
   *  porque são duas PERMISSÕES e dois assuntos — não porque a tela precise
   *  distinguir: os dois desembocam no mesmo refetch. */
  const CHANNELS: Array<{ path: string; event: string }> = [
    { path: "/sse/cash", event: "backstage-cash-update" },
    // A cozinha mexeu numa comanda deste balcão: o selo "Na cozinha" da linha
    // vira "Pronto" ou "Cancelado" sem ninguém apertar "Atualizar".
    { path: "/sse/tabs", event: "backstage-tabs-update" },
  ];

  function connectSse() {
    if (sources.length) return;
    realtime.value = "connecting";
    for (const channel of CHANNELS) {
      try {
        const source = new EventSource(ssePath(channel.path, config.app.baseURL), { withCredentials: true });
        // django-eventstream empurra eventos nomeados; qualquer um = refetch.
        const onEvent = () => onPush();
        ["message", channel.event].forEach((name) => source.addEventListener(name, onEvent));
        // Um stream vivo já tira a tela do poll; o outro caindo não a devolve
        // para lá, senão o canal saudável passaria a refazer fetch de graça.
        source.onopen = () => { realtime.value = "live"; };
        source.onerror = () => { if (!sources.some((s) => s.readyState === EventSource.OPEN)) realtime.value = "polling"; };
        sources.push(source);
      } catch {
        realtime.value = "polling";
      }
    }
  }

  function closeSse() {
    sources.forEach((source) => source.close());
    sources = [];
  }

  const onVisible = () => {
    if (document.visibilityState !== "visible") return;
    onPush();
    // Stream fechado de vez (ex.: conexão recusada antes do login)? Tenta de
    // novo — a sessão pode ter nascido desde então.
    if (sources.length && sources.every((s) => s.readyState === EventSource.CLOSED)) {
      closeSse();
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
    closeSse();
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  return { realtime };
}
