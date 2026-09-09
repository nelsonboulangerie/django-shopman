// O fato do forno é do SERVIDOR (ADR-021 §4): armar = enfornou, retirar =
// retirou; o Django carimba a hora no recebimento, como started_at/finished_at
// da WO — sem relógio de cliente. O countdown/alarme continua 100% local
// (useOvenTimers): aqui se DECLARAM os dois momentos com retry idempotente.
// A UI só altera o timer local depois da confirmação do servidor e mantém erro
// reconciliável no diálogo. Pausa, retomar e +N são UX local: não declaram nada.

import {
  armProductionOven,
  concludeProductionOven,
  type ProductionMutationCurrent,
  type QCKioskProjection,
} from "~/generated/productionContract";
import type { MaybeRefOrGetter } from "vue";
import { newProductionMutationKey } from "~/utils/api";
import {
  useProductionMutationGuard,
  type ProductionMutationMetadata,
} from "~/composables/useProductionMutationGuard";

export function useOvenFacts(
  projection: MaybeRefOrGetter<QCKioskProjection | null | undefined>,
  refreshProjection: () => unknown,
) {
  const mutationGuard = useProductionMutationGuard(
    projection,
    refreshProjection,
  );
  const latestRev = new Map<number, number>();
  const attempts = new Map<string, string>();
  const pending = ref<Set<number>>(new Set());
  const errors = ref<Map<number, string>>(new Map());

  async function declare(
    action: "arm" | "conclude",
    workOrderPk: number,
    expectedRev: number,
    request: (
      idempotencyKey: string,
      rev: number,
      metadata: ProductionMutationMetadata,
    ) => Promise<{ current: ProductionMutationCurrent | null }>,
  ): Promise<boolean> {
    const actionRef = `${action === "arm" ? "oven_arm" : "oven_conclude"}:${workOrderPk}`;
    const authorization = mutationGuard.authorizeMutation(actionRef);
    if (!authorization.ok) {
      errors.value = new Map(errors.value).set(
        workOrderPk,
        authorization.blocked.detail,
      );
      return false;
    }
    const attemptRef = `${action}:${workOrderPk}`;
    const idempotencyKey =
      attempts.get(attemptRef) ?? newProductionMutationKey();
    attempts.set(attemptRef, idempotencyKey);
    pending.value = new Set(pending.value).add(workOrderPk);
    errors.value = new Map(errors.value);
    errors.value.delete(workOrderPk);
    try {
      const response = await retryWithBackoff(
        () =>
          request(
            idempotencyKey,
            authorization.action.expected_rev ??
              latestRev.get(workOrderPk) ??
              expectedRev,
            authorization.metadata,
          ),
        { attempts: 4 },
      );
      if (response?.current) latestRev.set(workOrderPk, response.current.rev);
      await refreshProjection();
      attempts.delete(attemptRef);
      return true;
    } catch (error) {
      const message = httpErrorMessage(
        error,
        "Não foi possível confirmar o fato do forno. Tente novamente.",
      );
      errors.value = new Map(errors.value).set(workOrderPk, message);
      if (mutationGuard.handleMutationError(error)) return false;
      void reportClientError(error, {
        kind: "oven-fact",
        source: `production.${action}`,
      });
      return false;
    } finally {
      const next = new Set(pending.value);
      next.delete(workOrderPk);
      pending.value = next;
    }
  }

  /** Declara "enfornou" — o arm do timer. */
  const armed = (workOrderPk: number, rev: number, minutes: number) =>
    declare("arm", workOrderPk, rev, (idempotencyKey, expectedRev, metadata) =>
      armProductionOven(workOrderPk, {
        planned_seconds: Math.max(60, Math.round(minutes) * 60),
        expected_rev: expectedRev,
        ...metadata,
        idempotency_key: idempotencyKey,
      }),
    );

  /** Declara "retirou" ao abrir o QC. ``Visto`` no timer nunca mede. */
  const concluded = (workOrderPk: number, rev: number) =>
    declare(
      "conclude",
      workOrderPk,
      rev,
      (idempotencyKey, expectedRev, metadata) =>
        concludeProductionOven(workOrderPk, {
          expected_rev: expectedRev,
          ...metadata,
          idempotency_key: idempotencyKey,
        }),
    );

  const currentRev = (workOrderPk: number, fallback: number) =>
    latestRev.get(workOrderPk) ?? fallback;
  const isPending = (workOrderPk: number) => pending.value.has(workOrderPk);
  const errorFor = (workOrderPk: number) => errors.value.get(workOrderPk) ?? "";

  return { armed, concluded, currentRev, isPending, errorFor };
}
