// Quiosque de QC — read/write do fechamento de fornada (ADR-017 §9).
//   - useFetch da projection do quiosque (GET /api/v1/backstage/production/qc/);
//   - poll calmo de 30s (o quiosque é quem ESCREVE o estado; o poll só traz
//     fornadas fechadas por outras telas);
//   - finish com partição pela ordem do dia, quick-finish para fornada fora
//     do plano. Shortage estruturado sobe para o modal, como no KDS.
import type {
  ProductionQCResponse,
  ProductionShortageError,
} from "~/types/production";
import type { QcPartitionGroup } from "~/presentation/qc";
import {
  correctProductionQuality,
  finishProductionWorkOrder,
  quickFinishProduction,
} from "~/generated/productionContract";
import { parseShortage } from "~/presentation/production";
import { newProductionMutationKey } from "~/utils/api";
import {
  useProductionMutationGuard,
  type ProductionMutationBlock,
  type ProductionMutationMetadata,
} from "~/composables/useProductionMutationGuard";

export interface QcActResult {
  ok: boolean;
  shortage?: ProductionShortageError;
  blocked?: ProductionMutationBlock;
}

export function useQcKiosk(initialDate = "") {
  // "" = hoje (default do backend). Outra data serve à fornada esquecida de
  // ontem — o fechamento aceita qualquer dia com ordem aberta.
  const selectedDate = ref(initialDate);

  const { data, pending, error, refresh } = useFetch<ProductionQCResponse>(
    "/api/v1/backstage/production/qc/",
    {
      key: "production-qc",
      server: true,
      query: computed(() =>
        selectedDate.value ? { date: selectedDate.value } : {},
      ),
      onResponseError: operatorSessionOnError,
    },
  );

  const kiosk = computed(() => data.value?.qc ?? null);
  const mutationGuard = useProductionMutationGuard(kiosk, refresh);

  useAdaptivePoll(refresh, () => 30_000);

  const submitting = ref(false);
  const attempts = new Map<string, string>();

  async function post(
    attemptRef: string,
    request: (
      idempotencyKey: string,
      metadata: ProductionMutationMetadata,
    ) => Promise<unknown>,
    fallbackError = "Não deu para fechar a fornada. Tente de novo.",
  ): Promise<QcActResult> {
    if (submitting.value) return { ok: false };
    const authorization = mutationGuard.authorizeMutation(attemptRef);
    if (!authorization.ok) return { ok: false, blocked: authorization.blocked };
    submitting.value = true;
    const attempt = attempts.get(attemptRef) ?? newProductionMutationKey();
    attempts.set(attemptRef, attempt);
    try {
      await request(attempt, authorization.metadata);
      await refresh();
      attempts.delete(attemptRef);
      return { ok: true };
    } catch (err) {
      const shortage = parseShortage(httpError(err).data);
      if (shortage) return { ok: false, shortage };
      if (mutationGuard.handleMutationError(err)) return { ok: false };
      useSonner.error(httpErrorMessage(err, fallbackError));
      // Conflito de estado (fornada fechada/estornada em outra tela): o painel
      // está mentindo — atualiza na hora em vez de esperar o poll de 30s.
      if (httpErrorCode(err) === "conflict") await refresh();
      return { ok: false };
    } finally {
      submitting.value = false;
    }
  }

  const finish = (
    pk: number,
    rev: number,
    quantity: string,
    partition: QcPartitionGroup[],
    force = false,
    reason = "",
    yieldDeviationConfirmed = false,
    yieldDeviationReason = "",
    overrideProof = "",
  ) =>
    post(`finish:${pk}`, (idempotencyKey, metadata) =>
      finishProductionWorkOrder(pk, {
        quantity,
        partition,
        force,
        expected_rev:
          kiosk.value?.actions.find((action) => action.ref === `finish:${pk}`)
            ?.expected_rev ?? rev,
        yield_deviation_confirmed: yieldDeviationConfirmed,
        yield_deviation_reason: yieldDeviationReason.trim(),
        ...metadata,
        idempotency_key: idempotencyKey,
        ...(force ? { reason: reason.trim() } : {}),
        ...(force && overrideProof ? { override_proof: overrideProof } : {}),
      }),
    );

  // Fornada avulsa: plan + finish num passo, mesma partição. Sem
  // position_id — o backend resolve a posição padrão.
  const quickFinish = (
    recipeId: number,
    quantity: string,
    partition: QcPartitionGroup[],
    force = false,
    reason = "",
    overrideProof = "",
  ) =>
    post(`quick_finish:${recipeId}`, (idempotencyKey, metadata) =>
      quickFinishProduction({
        recipe_id: recipeId,
        quantity,
        partition,
        force,
        ...metadata,
        idempotency_key: idempotencyKey,
        ...(force ? { reason: reason.trim() } : {}),
        ...(force && overrideProof ? { override_proof: overrideProof } : {}),
      }),
    );

  const correctQuality = (
    pk: number,
    rev: number,
    partition: QcPartitionGroup[],
    reason: string,
  ): Promise<QcActResult> => {
    const auditReason = reason.trim();
    if (!auditReason) {
      useSonner.error("Informe o motivo da correção.");
      return Promise.resolve({ ok: false });
    }
    return post(
      `correct_qc:${pk}`,
      (idempotencyKey, metadata) =>
        correctProductionQuality(pk, {
          partition,
          reason: auditReason,
          expected_rev:
            kiosk.value?.actions.find(
              (action) => action.ref === `correct_qc:${pk}`,
            )?.expected_rev ?? rev,
          ...metadata,
          idempotency_key: idempotencyKey,
        }),
      "Não deu para salvar a correção de qualidade. Tente de novo.",
    );
  };

  return {
    kiosk,
    selectedDate,
    pending,
    error,
    refresh,
    submitting,
    finish,
    quickFinish,
    correctQuality,
  };
}
