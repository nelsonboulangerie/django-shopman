// Operator alerts read-side. Polls the active alerts + counts and exposes ack.
// The operator hub is the natural home for alerts (failed payments, low stock,
// stale orders…). Polling only (no SSE) — alerts are low-frequency.
import type { AlertProjection, AlertsResponse } from "~/types/production";
import { acknowledgeOperatorAlert } from "~/generated/productionContract";
import { useProductionMutationGuard } from "~/composables/useProductionMutationGuard";
import { newProductionMutationKey } from "~/utils/api";

export function useAlerts() {
  const { data, refresh } = useFetch<AlertsResponse>(
    "/api/v1/backstage/alerts/",
    {
      key: "operator-alerts",
      server: true,
    },
  );

  const alerts = computed<AlertProjection[]>(() => data.value?.alerts ?? []);
  const activeCount = computed(() => data.value?.counts?.active ?? 0);
  const criticalCount = computed(() => data.value?.counts?.critical ?? 0);
  const guardedProjection = computed(() => {
    if (!data.value) return null;
    return {
      generated_at: data.value.generated_at,
      source_revision: data.value.source_revision,
      fresh_until: data.value.fresh_until,
      contract_version: data.value.contract_version,
      actions: data.value.alerts.flatMap((alert) => alert.actions),
    };
  });
  const mutationGuard = useProductionMutationGuard(guardedProjection, refresh);
  const attempts = new Map<number, string>();
  const pending = ref<Set<number>>(new Set());

  useAdaptivePoll(refresh, () => 60_000);

  async function ack(alert: AlertProjection): Promise<void> {
    if (pending.value.has(alert.pk)) return;
    const authorization = mutationGuard.authorizeMutation(
      `acknowledge:${alert.pk}`,
    );
    if (!authorization.ok) return;
    const expectedRev = authorization.action.expected_rev;
    if (expectedRev === null) return;
    const idempotencyKey = attempts.get(alert.pk) ?? newProductionMutationKey();
    attempts.set(alert.pk, idempotencyKey);
    pending.value = new Set(pending.value).add(alert.pk);
    try {
      await retryWithBackoff(
        () =>
          acknowledgeOperatorAlert(alert.pk, {
            expected_rev: expectedRev,
            idempotency_key: idempotencyKey,
            ...authorization.metadata,
          }),
        { attempts: 4 },
      );
      await refresh();
      attempts.delete(alert.pk);
    } catch (err) {
      if (mutationGuard.handleMutationError(err)) return;
      useSonner.error(httpErrorMessage(err, "Falha ao reconhecer o alerta."));
    } finally {
      const next = new Set(pending.value);
      next.delete(alert.pk);
      pending.value = next;
    }
  }

  const isPending = (pk: number) => pending.value.has(pk);

  return { alerts, activeCount, criticalCount, refresh, ack, isPending };
}
