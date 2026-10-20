// Weighing read-side (per-prep tickets). Backs the "Por preparo" mode of the
// Preparação page and the blind-label print run: each ticket is one prep with
// its ingredients already scaled by the day's planned coefficient, plus the
// day's blind code (the only identity that goes on paper).
import type { Ref } from "vue";
import type {
  WeighingResponse,
  WeighingTicketProjection,
} from "~/types/production";
import { newProductionMutationKey } from "~/utils/mutationKey";
import { weighingRows } from "~/presentation/weighing";

export async function allocateColdWeighingProjection(
  current: WeighingResponse["weighing"] | null,
  allocationAttempts: Set<string>,
): Promise<WeighingResponse | null> {
  if (!current || current.codes_ready !== false) return null;
  const action = current.actions?.find(
    (candidate) => candidate.kind === "allocate_blind_codes" && candidate.enabled,
  );
  const attemptRef = current.source_revision;
  if (!action?.proof || !attemptRef || allocationAttempts.has(attemptRef)) return null;
  allocationAttempts.add(attemptRef);
  try {
    return await $fetch<WeighingResponse>(action.href, {
      method: "POST",
      body: {
        selected_date: current.selected_date,
        position: current.selected_position_ref,
        base_recipe: current.selected_base_recipe,
        idempotency_key: newProductionMutationKey(),
        projection_generated_at: current.generated_at,
        source_revision: current.source_revision,
        fresh_until: current.fresh_until,
        contract_version: current.contract_version,
        action_ref: action.ref,
        action_proof: action.proof,
      },
    });
  } catch {
    // O poll buscará uma revisão nova. Não repetimos a mesma autorização.
    return null;
  }
}

export function useWeighing(selectedDate: Ref<string>) {
  const { data, pending, error, refresh } = useFetch<WeighingResponse>(
    "/api/v1/backstage/production/weighing/",
    {
      key: "production-weighing",
      server: true,
      query: computed(() => ({ date: selectedDate.value })),
      onResponseError: operatorSessionOnError,
    },
  );

  const projection = computed(() => data.value?.weighing ?? null);
  const tickets = computed<WeighingTicketProjection[]>(
    () => data.value?.weighing?.tickets ?? [],
  );
  const dateDisplay = computed(
    () => data.value?.weighing?.selected_date_display ?? "",
  );

  // GET nunca aloca códigos. Uma projeção fria oferece um comando explícito;
  // cada revisão o dispara no máximo uma vez e substitui o dado local pela
  // resposta já pronta do POST, sem ciclo GET→POST→GET.
  const allocationAttempts = new Set<string>();
  watch(
    projection,
    async (current) => {
      if (!import.meta.client) return;
      const ready = await allocateColdWeighingProjection(current, allocationAttempts);
      if (ready) data.value = ready;
    },
    { immediate: true },
  );

  useAdaptivePoll(refresh, () => 60_000);

  // Massa velha é escolha do padeiro na bancada, preparo a preparo: estado
  // local da tela. O servidor já mandou a mistura final no teto
  // (`ticket.old_dough`); aqui só se escolhe qual das duas listas pesar.
  const oldDoughKeys = ref<Set<string>>(new Set());
  function usesOldDough(key: string): boolean {
    return oldDoughKeys.value.has(key);
  }
  function setOldDough(key: string, on: boolean) {
    const next = new Set(oldDoughKeys.value);
    if (on) next.add(key);
    else next.delete(key);
    oldDoughKeys.value = next;
  }
  function rowsFor(ticket: WeighingTicketProjection, key: string) {
    return weighingRows(ticket, usesOldDough(key) && !!ticket.old_dough);
  }

  return {
    projection,
    tickets,
    dateDisplay,
    pending,
    error,
    refresh,
    usesOldDough,
    setOldDough,
    rowsFor,
  };
}
