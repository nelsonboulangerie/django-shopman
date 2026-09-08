// Production live-floor read-side. Single source for the started-WorkOrder board:
//   - useFetch the production KDS projection (GET /api/v1/backstage/production/kds/);
//   - adaptive poll: 30s routine, 10s while something runs late, paused hidden.
// Writes go through the django proxy (CSRF handled there) and reconcile via refresh.
// Material/order shortage is surfaced as a structured error so the page can open
// the shortage modal (a finish can be retried with force=1).
import type { ProductionKDSCardProjection, ProductionKDSResponse, ProductionShortageError } from "~/types/production";
import {
  advanceProductionWorkOrderStep,
  voidProductionWorkOrder,
} from "~/generated/productionContract";
import { parseShortage } from "~/presentation/production";
import { newProductionMutationKey } from "~/utils/api";

export interface ActResult {
  ok: boolean;
  shortage?: ProductionShortageError;
}

export function useProductionKds() {
  const path = "/api/v1/backstage/production/kds/";

  const { data, pending, error, refresh } = useFetch<ProductionKDSResponse>(path, {
    key: "production-kds",
    server: true,
    onResponseError: operatorSessionOnError,
  });

  const cards = computed<ProductionKDSCardProjection[]>(() => data.value?.kds?.cards ?? []);
  const totalCount = computed(() => data.value?.kds?.total_count ?? 0);
  const lateCount = computed(() => data.value?.kds?.late_count ?? 0);

  // Cadência sobe sob pressão: algo atrasado no chão → 10s; rotina → 30s.
  useAdaptivePoll(refresh, () => (lateCount.value > 0 ? 10_000 : 30_000));

  // per-WO in-flight guard (disables that card's buttons); POST then reconcile.
  const busy = ref<Set<number>>(new Set());
  const attempts = new Map<string, string>();
  const isBusy = (pk: number) => busy.value.has(pk);

  async function post(
    pk: number,
    action: string,
    request: (idempotencyKey: string) => Promise<unknown>,
  ): Promise<ActResult> {
    if (busy.value.has(pk)) return { ok: false };
    busy.value = new Set(busy.value).add(pk);
    const attemptRef = `${action}:${pk}`;
    const attempt = attempts.get(attemptRef) ?? newProductionMutationKey();
    attempts.set(attemptRef, attempt);
    try {
      await request(attempt);
      await refresh();
      attempts.delete(attemptRef);
      return { ok: true };
    } catch (err) {
      const shortage = parseShortage(httpError(err).data);
      if (shortage) return { ok: false, shortage };
      useSonner.error(httpErrorMessage(err, "Falha na ação. Tente de novo."));
      return { ok: false };
    } finally {
      const next = new Set(busy.value);
      next.delete(pk);
      busy.value = next;
    }
  }

  const advanceStep = (pk: number, rev: number) =>
    post(pk, "advance-step", (idempotencyKey) =>
      advanceProductionWorkOrderStep(pk, {
        expected_rev: rev,
        idempotency_key: idempotencyKey,
      }),
    );
  // O finish não vive mais aqui: fechar a fornada é a Expedição (quiosque de
  // QC, useQcKiosk), sempre com partição — ADR-017 §9.
  const voidOrder = (pk: number, rev: number, reason: string) =>
    post(pk, "void", (idempotencyKey) =>
      voidProductionWorkOrder(pk, {
        reason,
        expected_rev: rev,
        idempotency_key: idempotencyKey,
      }),
    );

  return { cards, totalCount, lateCount, pending, error, refresh, isBusy, advanceStep, voidOrder };
}
