// Operator alerts read-side. SSE-first (ADR-016): o push do canal de alertas
// (`/sse/alerts` no BFF → backstage-alerts-main no Django) só avisa "chegou
// algo" e dispara o refetch; o fetch REST segue sendo a fonte da verdade e o
// poll de 60s vira rede de segurança em cadência calma.
import type { AlertProjection, AlertsResponse } from "~/types/orders";

export function useAlerts() {
  const config = useRuntimeConfig();
  const { data, refresh } = useFetch<AlertsResponse>("/api/v1/backstage/alerts/", {
    key: "operator-alerts",
    server: true,
  });

  const alerts = computed<AlertProjection[]>(() => data.value?.alerts ?? []);
  const activeCount = computed(() => data.value?.counts?.active ?? 0);
  const criticalCount = computed(() => data.value?.counts?.critical ?? 0);

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: EventSource | null = null;

  function connectSse() {
    if (source) return;
    const url = ssePath("/sse/alerts", config.app.baseURL);
    try {
      source = new EventSource(url, { withCredentials: true });
      // O corpo é sinal mínimo (id/tipo/severidade); quem recebe refaz o fetch.
      ["message", "backstage-alerts-update"].forEach((name) =>
        source!.addEventListener(name, () => refresh()),
      );
    } catch {
      source = null; // sem SSE o poll de 60s segura sozinho
    }
  }

  onMounted(() => {
    pollTimer = setInterval(() => refresh(), 60_000);
    connectSse();
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (source) { source.close(); source = null; }
  });

  async function ack(pk: number): Promise<void> {
    try {
      await $fetch(`/api/v1/backstage/alerts/${pk}/ack/`, { method: "POST", body: {} });
      await refresh();
    } catch (error) {
      useSonner.error(httpErrorMessage(error, "Falha ao reconhecer o alerta."));
    }
  }

  return { alerts, activeCount, criticalCount, refresh, ack };
}
