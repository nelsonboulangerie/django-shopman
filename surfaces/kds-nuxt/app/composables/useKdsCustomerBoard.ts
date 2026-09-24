// Customer pickup board read-side (Arc 4). Public endpoint (no auth) —
// GET /api/v1/backstage/kds/pickup/ → orders split into preparing / ready, with
// privacy-safe refs only. Polls every 10s (mirrors the HTMX board); SSE
// same-origin via BFF (/sse/orders) is best-effort, poll covers the gaps.
import type {
  KDSCustomerStatusProjection,
  KDSCustomerStatusResponse,
} from "~/types/kds";

import { openResilientEventSource, type ResilientEventSource } from "../../../operator-kit/app/utils/resilientEventSource";

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
    // Same-origin sempre: o BFF (server/routes/sse/orders.ts) faz streaming do
    // eventstream do Django, em dev e em prod — nada de gate por origem.
    // O painel é público: sem sessão o Django recusa o canal com `stream-error`,
    // e o EventSource cru reconectava a cada ~3 s com a bolinha "ao vivo"
    // piscando. O do kit espera cada vez mais (teto de 60 s) e se recria depois
    // do 502 de deploy; o poll de 10 s segura a TV nos dois casos.
    realtime.value = "connecting";
    source = openResilientEventSource({
      url: ssePath("/sse/orders", config.app.baseURL),
      events: ["backstage-orders-update"],
      onEvent: () => { refresh(); },
      onOpen: (reconnected) => {
        realtime.value = "live";
        if (reconnected) refresh();
      },
      onDown: () => { realtime.value = "polling"; },
    });
  }

  onMounted(() => {
    pollTimer = setInterval(() => refresh(), 10_000);
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
