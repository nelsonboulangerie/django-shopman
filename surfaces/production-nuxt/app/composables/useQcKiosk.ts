// Quiosque de QC — read/write do fechamento de fornada (ADR-017 §9).
//   - useFetch da projection do quiosque (GET /api/v1/backstage/production/qc/);
//   - poll calmo de 30s (o quiosque é quem ESCREVE o estado; o poll só traz
//     fornadas fechadas por outras telas);
//   - finish com partição pela ordem do dia, quick-finish para fornada fora
//     do plano. Shortage estruturado sobe para o modal, como no KDS.
import type { ProductionQCResponse, ProductionShortageError } from "~/types/production";
import type { QcPartitionGroup } from "~/presentation/qc";
import { parseShortage } from "~/presentation/production";

export interface QcActResult {
  ok: boolean;
  shortage?: ProductionShortageError;
}

export function useQcKiosk() {
  // "" = hoje (default do backend). Outra data serve à fornada esquecida de
  // ontem — o fechamento aceita qualquer dia com ordem aberta.
  const selectedDate = ref("");

  const { data, pending, error, refresh } = useFetch<ProductionQCResponse>(
    "/api/v1/backstage/production/qc/",
    {
      key: "production-qc",
      server: true,
      query: computed(() => (selectedDate.value ? { date: selectedDate.value } : {})),
      onResponseError: operatorSessionOnError,
    },
  );

  const kiosk = computed(() => data.value?.qc ?? null);

  useAdaptivePoll(refresh, () => 30_000);

  const submitting = ref(false);

  async function post(url: string, body: Record<string, unknown>): Promise<QcActResult> {
    if (submitting.value) return { ok: false };
    submitting.value = true;
    try {
      await $fetch(url, { method: "POST", body });
      await refresh();
      return { ok: true };
    } catch (err) {
      const shortage = parseShortage(httpError(err).data);
      if (shortage) return { ok: false, shortage };
      useSonner.error(httpErrorMessage(err, "Não deu para fechar a fornada. Tente de novo."));
      // Conflito de estado (fornada fechada/estornada em outra tela): o painel
      // está mentindo — atualiza na hora em vez de esperar o poll de 30s.
      if (httpErrorCode(err) === "state_conflict") await refresh();
      return { ok: false };
    } finally {
      submitting.value = false;
    }
  }

  const finish = (pk: number, quantity: string, partition: QcPartitionGroup[], force = false) =>
    post(`/api/v1/backstage/production/${pk}/finish/`, { quantity, partition, force });

  // Fornada avulsa: plan + finish num passo, mesma partição. Sem
  // position_id — o backend resolve a posição padrão.
  const quickFinish = (
    recipeId: number,
    quantity: string,
    partition: QcPartitionGroup[],
    force = false,
  ) =>
    post("/api/v1/backstage/production/quick-finish/", {
      recipe_id: recipeId,
      quantity,
      partition,
      force,
    });

  return { kiosk, selectedDate, pending, error, refresh, submitting, finish, quickFinish };
}
