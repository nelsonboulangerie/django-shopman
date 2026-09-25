import { useOperatorResourceKey } from "./useOperatorResourceKey";
// Operator alerts read-side. SSE-first (ADR-016): o push do canal de alertas
// (`/sse/alerts` no BFF → backstage-alerts-main no Django) só avisa "chegou
// algo" e dispara o refetch; o fetch REST segue sendo a fonte da verdade e o
// poll de 60s vira rede de segurança em cadência calma.
//
// `scope=orders`: o sino do Gestor mostra só o que é de pedido. Infraestrutura,
// marketing e B.I. ficam no Admin, onde alguém pode agir.
import type { AlertProjection, AlertsResponse } from "~/types/orders";

function newAckKey(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  return uuid || `ack-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function useAlerts() {
  const config = useRuntimeConfig();
  const { data, refresh } = useFetch<AlertsResponse>("/api/v1/backstage/alerts/", {
    key: useOperatorResourceKey("operator-alerts"),
    query: { scope: "orders" },
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

  /** O alerta ainda não foi marcado como visto (o servidor oferece o gesto). */
  function ackAction(alert: AlertProjection) {
    return alert.actions?.find((action) => action.kind === "acknowledge_alert" && action.enabled) ?? null;
  }

  // Uma chave por alerta, mantida entre tentativas: o servidor deduplica.
  const attempts = new Map<number, string>();

  /**
   * "Visto": registra que alguém leu. O alerta continua no sino até a causa
   * acabar, porque é o sistema que confirma que ela acabou.
   *
   * O servidor só aceita o gesto que ele mesmo ofereceu na leitura atual
   * (ação, revisão e prova da projeção). Antes o corpo ia vazio e todo toque
   * caía em 400.
   */
  async function ack(alert: AlertProjection): Promise<void> {
    const action = ackAction(alert);
    const read = data.value;
    if (!action || !read?.source_revision) return;
    const key = attempts.get(alert.pk) ?? newAckKey();
    attempts.set(alert.pk, key);
    try {
      await $fetch(`/api/v1/backstage/alerts/${alert.pk}/ack/`, {
        method: "POST",
        body: {
          idempotency_key: key,
          expected_rev: action.expected_rev ?? 0,
          projection_generated_at: read.generated_at,
          source_revision: read.source_revision,
          fresh_until: read.fresh_until,
          contract_version: read.contract_version,
          action_ref: action.ref,
          action_proof: action.proof,
        },
      });
      attempts.delete(alert.pk);
      await refresh();
    } catch (error) {
      if (httpError(error).status === 409) {
        // A leitura venceu ou o alerta mudou: relê e deixa o operador tocar de novo.
        attempts.delete(alert.pk);
        await refresh();
        useSonner.error("Os alertas mudaram. Confira e toque em Visto de novo.");
        return;
      }
      useSonner.error(httpErrorMessage(error, "Não deu para marcar o alerta como visto. Tente de novo."));
    }
  }

  return { alerts, activeCount, criticalCount, refresh, ack, ackAction };
}
