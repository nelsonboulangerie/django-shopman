// O fato do forno é do SERVIDOR (ADR-021 §4): armar = enfornou, Concluir =
// retirou; o Django carimba a hora no recebimento, como started_at/finished_at
// da WO — sem relógio de cliente. O countdown/alarme continua 100% local
// (useOvenTimers): aqui só se DECLARAM os dois momentos, fire-and-forget com
// retry — a UI do forneiro nunca espera rede. Falha terminal não vira toast às
// 5h da manhã; vira relato de erro, e o relatório de tempo declara a cobertura
// em vez de fingir medição. Pausa, retomar e +N são UX local: não declaram nada.

import { newProductionMutationKey } from "~/utils/api";

export function useOvenFacts() {
  const latestRev = new Map<number, number>();

  function declare(
    workOrderPk: number,
    path: string,
    expectedRev: number,
    body?: Record<string, unknown>,
  ): Promise<void> {
    const idempotencyKey = newProductionMutationKey();
    // $fetch<unknown>: fixa o tipo de retorno e poupa o TS de inferir a união
    // de rotas tipadas do Nitro dentro do genérico do retryWithBackoff.
    return retryWithBackoff<{ current?: { rev: number } }>(() => $fetch<{
      current?: { rev: number };
    }>(path, {
      method: "POST",
      body: {
        ...(body ?? {}),
        expected_rev: latestRev.get(workOrderPk) ?? expectedRev,
        idempotency_key: idempotencyKey,
      },
    }), {
      attempts: 4,
    })
      .then((response) => {
        if (response.current) latestRev.set(workOrderPk, response.current.rev);
      })
      .catch((error) => {
        void reportClientError(error, { kind: "oven-fact", source: path });
      });
  }

  /** Declara "enfornou" — o arm do timer. */
  const armed = (workOrderPk: number, rev: number, minutes: number) =>
    declare(workOrderPk, `/api/v1/backstage/production/${workOrderPk}/oven/arm/`, rev, {
      planned_seconds: Math.max(60, Math.round(minutes) * 60),
    });

  /** Declara "retirou" — o Concluir do timer. Só ele; expiração não mede. */
  const concluded = (workOrderPk: number, rev: number) =>
    declare(workOrderPk, `/api/v1/backstage/production/${workOrderPk}/oven/conclude/`, rev);

  const currentRev = (workOrderPk: number, fallback: number) =>
    latestRev.get(workOrderPk) ?? fallback;

  return { armed, concluded, currentRev };
}
