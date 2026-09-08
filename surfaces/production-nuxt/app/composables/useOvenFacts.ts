// O fato do forno é do SERVIDOR (ADR-021 §4): armar = enfornou, Concluir =
// retirou; o Django carimba a hora no recebimento, como started_at/finished_at
// da WO — sem relógio de cliente. O countdown/alarme continua 100% local
// (useOvenTimers): aqui se DECLARAM os dois momentos com retry idempotente.
// A UI só altera o timer local depois da confirmação do servidor e mantém erro
// reconciliável no diálogo. Pausa, retomar e +N são UX local: não declaram nada.

import {
  armProductionOven,
  concludeProductionOven,
  type ProductionMutationCurrent,
} from "~/generated/productionContract";
import { newProductionMutationKey } from "~/utils/api";

export function useOvenFacts() {
  const latestRev = new Map<number, number>();
  const attempts = new Map<string, string>();
  const pending = ref<Set<number>>(new Set());
  const errors = ref<Map<number, string>>(new Map());

  async function declare(
    action: "arm" | "conclude",
    workOrderPk: number,
    expectedRev: number,
    request: (idempotencyKey: string, rev: number) => Promise<{ current: ProductionMutationCurrent | null }>,
  ): Promise<boolean> {
    const attemptRef = `${action}:${workOrderPk}`;
    const idempotencyKey = attempts.get(attemptRef) ?? newProductionMutationKey();
    attempts.set(attemptRef, idempotencyKey);
    pending.value = new Set(pending.value).add(workOrderPk);
    errors.value = new Map(errors.value);
    errors.value.delete(workOrderPk);
    try {
      const response = await retryWithBackoff(
        () => request(idempotencyKey, latestRev.get(workOrderPk) ?? expectedRev),
        { attempts: 4 },
      );
      if (response?.current) latestRev.set(workOrderPk, response.current.rev);
      attempts.delete(attemptRef);
      return true;
    } catch (error) {
      const message = httpErrorMessage(
        error,
        "Não foi possível confirmar o fato do forno. Tente novamente.",
      );
      errors.value = new Map(errors.value).set(workOrderPk, message);
      void reportClientError(error, { kind: "oven-fact", source: `production.${action}` });
      return false;
    } finally {
      const next = new Set(pending.value);
      next.delete(workOrderPk);
      pending.value = next;
    }
  }

  /** Declara "enfornou" — o arm do timer. */
  const armed = (workOrderPk: number, rev: number, minutes: number) =>
    declare("arm", workOrderPk, rev, (idempotencyKey, expectedRev) =>
      armProductionOven(workOrderPk, {
        planned_seconds: Math.max(60, Math.round(minutes) * 60),
        expected_rev: expectedRev,
        idempotency_key: idempotencyKey,
      }),
    );

  /** Declara "retirou" — o Concluir do timer. Só ele; expiração não mede. */
  const concluded = (workOrderPk: number, rev: number) =>
    declare("conclude", workOrderPk, rev, (idempotencyKey, expectedRev) =>
      concludeProductionOven(workOrderPk, {
        expected_rev: expectedRev,
        idempotency_key: idempotencyKey,
      }),
    );

  const currentRev = (workOrderPk: number, fallback: number) =>
    latestRev.get(workOrderPk) ?? fallback;
  const isPending = (workOrderPk: number) => pending.value.has(workOrderPk);
  const errorFor = (workOrderPk: number) => errors.value.get(workOrderPk) ?? "";

  return { armed, concluded, currentRev, isPending, errorFor };
}
