// Production planning read-side. Single source for the planning matrix:
//   - useFetch the production board projection (GET /api/v1/backstage/production/);
//   - poll every 60s (planning changes slowly, manager-paced).
// Writes (plan / start) go through the django proxy (CSRF handled there) and
// reconcile via refresh. Order-coverage shortage surfaces as a structured error.
import type {
  ProductionBoardProjection,
  ProductionBoardResponse,
  ProductionShortageError,
} from "~/types/production";
import {
  planProduction,
  startProductionWorkOrder,
  type ProductionPlanMutationRequest,
} from "~/generated/productionContract";
import {
  isoForOffset,
  parseShortage,
  storeHour,
} from "~/presentation/production";
import { newProductionMutationKey } from "~/utils/api";
import {
  useProductionMutationGuard,
  type ProductionMutationBlock,
  type ProductionMutationMetadata,
} from "~/composables/useProductionMutationGuard";

export interface BoardActResult {
  ok: boolean;
  shortage?: ProductionShortageError;
  blocked?: ProductionMutationBlock;
}

/** ISO date default for planning: today's board in the morning, tomorrow's
 *  after noon — o padeiro planeja o dia seguinte na calmaria da tarde. */
export function defaultPlanningDate(now = new Date()): string {
  return isoForOffset(storeHour(now) >= 12 ? 1 : 0, now);
}

export function useProductionBoard(
  initialDate: string = defaultPlanningDate(),
) {
  const path = "/api/v1/backstage/production/";
  const selectedDate = ref(initialDate);

  const { data, pending, error, refresh } = useFetch<ProductionBoardResponse>(
    path,
    {
      key: "production-board",
      server: true,
      query: computed(() => ({ date: selectedDate.value })),
      onResponseError: operatorSessionOnError,
    },
  );

  const board = computed<ProductionBoardProjection | null>(
    () => data.value?.board ?? null,
  );
  const mutationGuard = useProductionMutationGuard(board, refresh);
  const rows = computed(() => board.value?.matrix_rows ?? []);
  const counts = computed(() => board.value?.counts ?? null);
  const dateDisplay = computed(() => board.value?.selected_date_display ?? "");

  useAdaptivePoll(refresh, () => 60_000);

  // a planning POST keys on the output_sku row (one in-flight per row).
  const busy = ref<Set<string>>(new Set());
  const attempts = new Map<string, string>();
  const isBusy = (key: string) => busy.value.has(key);

  async function post(
    key: string,
    actionRef: string,
    action: (
      idempotencyKey: string,
      metadata: ProductionMutationMetadata,
      expectedRev: number | null,
    ) => Promise<unknown>,
  ): Promise<BoardActResult> {
    if (busy.value.has(key)) return { ok: false };
    const authorization = mutationGuard.authorizeMutation(actionRef);
    if (!authorization.ok) return { ok: false, blocked: authorization.blocked };
    busy.value = new Set(busy.value).add(key);
    const attempt = attempts.get(key) ?? newProductionMutationKey();
    attempts.set(key, attempt);
    try {
      await action(
        attempt,
        authorization.metadata,
        authorization.action.expected_rev,
      );
      await refresh();
      attempts.delete(key);
      return { ok: true };
    } catch (err) {
      const shortage = parseShortage(httpError(err).data);
      if (shortage) return { ok: false, shortage };
      if (mutationGuard.handleMutationError(err)) return { ok: false };
      useSonner.error(httpErrorMessage(err, "Falha na ação. Tente de novo."));
      return { ok: false };
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // ⚠️ `expected_rev` é a revisão que ESTE quadro leu, e é o que impede duas bancadas
  // de se sobrescreverem. A bancada A ajusta para 40 enquanto a B ajusta para 25 sobre
  // um quadro de sessenta segundos de idade: sem o número, o último POST vence, sem 409
  // e sem aviso. Com ele, a segunda recebe "a fornada mudou em outra tela".
  //
  // Nulo quando o card não é conhecido (planejar uma linha que ainda não tem
  // fornada): não há revisão anterior para comparar, e mandar zero afirmaria uma coisa
  // falsa. O contrato exige que essa ausência seja explícita.
  function plan(
    key: string,
    payload: Omit<
      ProductionPlanMutationRequest,
      "idempotency_key" | keyof ProductionMutationMetadata
    >,
  ): Promise<BoardActResult> {
    const actionPrefix =
      payload.source === "suggested" ? "plan_suggested" : "plan";
    const actionTarget = payload.work_order_id
      ? String(payload.work_order_id)
      : `${payload.recipe_id}:${payload.target_date}:${payload.position_ref}`;
    const normalizedQuantity = String(payload.quantity)
      .replace(/(\.\d*?)0+$/, "$1")
      .replace(/\.$/, "");
    const actionRef = `${actionPrefix}:${actionTarget}${
      actionPrefix === "plan_suggested" ? `:${normalizedQuantity}` : ""
    }`;
    return post(key, actionRef, (idempotencyKey, metadata, expectedRev) =>
      planProduction({
        ...payload,
        expected_rev: expectedRev,
        ...metadata,
        idempotency_key: idempotencyKey,
      }),
    );
  }

  function start(
    key: string,
    woPk: number,
    rev: number,
    quantity: string,
  ): Promise<BoardActResult> {
    return post(key, `start:${woPk}`, (idempotencyKey, metadata, expectedRev) =>
      startProductionWorkOrder(woPk, {
        quantity,
        expected_rev: expectedRev ?? rev,
        ...metadata,
        idempotency_key: idempotencyKey,
      }),
    );
  }

  return {
    board,
    rows,
    counts,
    dateDisplay,
    selectedDate,
    pending,
    error,
    refresh,
    isBusy,
    plan,
    start,
  };
}
