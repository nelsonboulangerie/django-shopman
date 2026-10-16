// Customer pickup board read-side (Arc 4). Public endpoint (no auth) —
// GET /api/v1/backstage/kds/pickup/ → orders split into preparing / ready, with
// privacy-safe refs only. SSE-first (ADR-016): o canal público `pickup-board`
// (BFF /sse/pickup) avisa a cada mudança da cozinha ou do pedido, e o painel
// refaz o GET. O poll de 30 s só cobre a queda do stream.
import type {
  KDSCustomerStatusProjection,
  KDSCustomerStatusResponse,
} from "~/types/kds";

import { openResilientEventSource, type ResilientEventSource } from "../../../operator-kit/app/utils/resilientEventSource";

/** Poll de reserva do painel; a atualização normal chega pelo SSE. */
export const PICKUP_FALLBACK_POLL_MS = 30_000;

export function useKdsCustomerBoard() {
  const config = useRuntimeConfig();
  const { data, pending, error, refresh } = useFetch<KDSCustomerStatusResponse>(
    "/api/v1/backstage/kds/pickup/",
    { key: "kds-customer-board" },
  );
  const status = computed<KDSCustomerStatusProjection | null>(
    () => data.value?.status ?? null,
  );

  // `realtime` diz HONESTAMENTE se o painel está recebendo push (SSE) ou só fazendo poll —
  // a bolinha verde "ao vivo" só acende quando o EventSource conecta de fato (onopen).
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: ResilientEventSource | null = null;

  function connectSse() {
    if (source) return;
    // Same-origin sempre: o BFF (server/routes/sse/pickup.ts) faz streaming do
    // eventstream do Django, em dev e em prod — nada de gate por origem.
    // O canal é `pickup-board`, público e de corpo vazio. Antes o painel ouvia
    // `backstage-orders-main`: a TV sem sessão (ou com a do caixa) levava
    // `stream-error` "Permission denied", e o Pronto da cozinha numa comanda
    // nem era publicado ali, então a TV vivia do poll (alpha, 13/10/2026).
    // O EventSource do kit espera cada vez mais (teto de 60 s) e se recria
    // depois do 502 de deploy; o poll segura a TV no meio tempo.
    realtime.value = "connecting";
    source = openResilientEventSource({
      url: ssePath("/sse/pickup", config.app.baseURL),
      events: ["pickup-board-update"],
      onEvent: () => { refresh(); },
      onOpen: (reconnected) => {
        realtime.value = "live";
        if (reconnected) refresh();
      },
      onDown: () => { realtime.value = "polling"; },
    });
  }

  onMounted(() => {
    // Fallback calmo: com o SSE vivo o painel muda no evento; sem ele, nunca
    // passa de 30 s parado.
    pollTimer = setInterval(() => refresh(), PICKUP_FALLBACK_POLL_MS);
    connectSse();
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (source) {
      source.close();
      source = null;
    }
  });

  return { status, realtime, pending, error, refresh };
}
