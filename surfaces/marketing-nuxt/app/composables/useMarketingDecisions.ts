// A fila de decisões: a casa do Marketing, o sino e o "Agendados" leem esta
// mesma resposta (uma chave de `useFetch` só, então um fetch só por tela).
//
// ADR-016 (SSE-first): o canal pessoal (`/sse/notifications`, aberto pela caixa
// do sino) só avisa que algo mudou; a VERDADE é o refetch da fila. A caixa também
// faz o poll de rede de segurança (60 s) e publica a mesma revisão, então quem
// escuta a revisão recebe as duas coisas.
//
// ⚠️ Só UMA instância escuta a revisão (`live: true`), a do sino, que está
// montado em todas as telas. Se cada leitor escutasse, cada aviso dispararia um
// refetch por leitor da mesma chave.
import { NOTIFICATION_REVISION_STATE } from "~/composables/useMarketingNotificationInbox";
import type { DecisionQueue, DecisionQueueResponse } from "~/types/decisions";

export const DECISIONS_URL = "/api/v1/backstage/marketing/decisions/";

export function useMarketingDecisions(options: { live?: boolean } = {}) {
  const { data, refresh, pending, error } = useFetch<DecisionQueueResponse>(
    DECISIONS_URL,
    {
      key: "marketing-decisions",
      server: true,
      onResponseError: marketingSessionOnError,
    },
  );

  const queue = computed<DecisionQueue | null>(() => data.value?.queue ?? null);
  const items = computed(() => queue.value?.items ?? []);
  const automaticChecks = computed(() => queue.value?.automatic_checks ?? []);
  const scheduled = computed(() => queue.value?.scheduled ?? []);
  const decisionCount = computed(() => items.value.length);
  const shopTimezone = computed(() => queue.value?.shop_timezone ?? "UTC");

  // O relógio da tela anda sozinho: "faltam 12 min" vira "faltam 11 min" sem
  // depender de o servidor mandar a mesma fila de novo. O valor inicial viaja do
  // SSR no `useState`, para a hidratação ler o mesmo "faltam N min" do servidor.
  const nowMs = useState<number>("marketing-decisions-now", () => Date.now());
  let clockTimer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => {
    nowMs.value = Date.now();
    clockTimer = setInterval(() => {
      nowMs.value = Date.now();
    }, 30_000);
  });
  onBeforeUnmount(() => {
    if (clockTimer) clearInterval(clockTimer);
  });

  if (options.live) {
    const notificationRevision = useState<number>(
      NOTIFICATION_REVISION_STATE,
      () => 0,
    );
    watch(notificationRevision, () => void refresh());
  }

  return {
    queue,
    items,
    automaticChecks,
    scheduled,
    decisionCount,
    shopTimezone,
    nowMs,
    loading: pending,
    error,
    refresh,
  };
}
