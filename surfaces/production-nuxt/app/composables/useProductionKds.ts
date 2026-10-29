// Production live-floor read-side. Single source for the started-WorkOrder board:
//   - useFetch the production KDS projection (GET /api/v1/backstage/production/kds/);
//   - adaptive poll: 30s routine, 10s while something runs late, paused hidden.
// Writes go through the django proxy (CSRF handled there) and reconcile via refresh.
// Material/order shortage is surfaced as a structured error so the page can open
// the shortage modal (a finish can be retried with force=1).
import type {
  ProductionActionProjection,
  ProductionKDSCardProjection,
  ProductionKDSResponse,
  ProductionShortageError,
} from "~/types/production";
import { voidProductionWorkOrder } from "~/generated/productionContract";
import { parseShortage } from "~/presentation/production";
import { newProductionMutationKey } from "~/utils/mutationKey";
import {
  useProductionMutationGuard,
  type ProductionMutationBlock,
  type ProductionMutationMetadata,
} from "~/composables/useProductionMutationGuard";

export interface ActResult<T = unknown> {
  ok: boolean;
  data?: T;
  shortage?: ProductionShortageError;
  blocked?: ProductionMutationBlock;
}

export interface RegisterOldDoughInput {
  quantity: string;
  unit: "g" | "kg";
  expiryDate: string;
  positionRef?: string;
  note?: string;
}

export interface RegisterOldDoughResponse {
  ok: boolean;
  sku: string;
  name: string;
  batch_ref: string;
  quantity_g: string;
  expiry_date: string;
  recipe_version_ref: string;
  replayed: boolean;
}

export interface AuthorizeFormulaDeviationInput {
  ingredientRef: string;
  actualQuantity: string;
  batchRef?: string;
  reason: string;
}

export interface AuthorizeFormulaDeviationResponse {
  ok: boolean;
  ingredient_ref: string;
  ingredient_sku: string;
  ingredient_name: string;
  expected: {
    minimum: string | null;
    target: string;
    maximum: string | null;
  };
  actual: string;
  reason: string;
  impact: {
    bom: Array<{ sku: string; quantity: string; unit: string }>;
    batch_ref: string;
  };
  work_order_rev: number;
  replayed: boolean;
}

export function useProductionKds() {
  const path = "/api/v1/backstage/production/kds/";

  const { data, pending, error, refresh } = useFetch<ProductionKDSResponse>(path, {
    key: "production-kds",
    server: true,
    onResponseError: operatorSessionOnError,
  });

  const kds = computed(() => data.value?.kds ?? null);
  const mutationGuard = useProductionMutationGuard(kds, refresh);
  const cards = computed<ProductionKDSCardProjection[]>(() => kds.value?.cards ?? []);
  const totalCount = computed(() => data.value?.kds?.total_count ?? 0);
  const lateCount = computed(() => data.value?.kds?.late_count ?? 0);
  const actionFor = (ref: string): ProductionActionProjection | undefined =>
    kds.value?.actions.find((action) => action.ref === ref);

  // Cadência sobe sob pressão: algo atrasado no chão → 10s; rotina → 30s.
  useAdaptivePoll(refresh, () => (lateCount.value > 0 ? 10_000 : 30_000));

  // per-WO in-flight guard (disables that card's buttons); POST then reconcile.
  const busy = ref<Set<number>>(new Set());
  const attempts = new Map<string, string>();
  const isBusy = (pk: number) => busy.value.has(pk);

  async function post<T = unknown>(
    pk: number,
    action: string,
    request: (
      idempotencyKey: string,
      metadata: ProductionMutationMetadata,
      projectedAction: ProductionActionProjection,
    ) => Promise<T>,
  ): Promise<ActResult<T>> {
    if (busy.value.has(pk)) return { ok: false };
    const actionRef = `${action}:${pk}`;
    const authorization = mutationGuard.authorizeMutation(actionRef);
    if (!authorization.ok) return { ok: false, blocked: authorization.blocked };
    const projectedAction = actionFor(actionRef);
    if (!projectedAction) return { ok: false };
    busy.value = new Set(busy.value).add(pk);
    const attemptRef = actionRef;
    const attempt = attempts.get(attemptRef) ?? newProductionMutationKey();
    attempts.set(attemptRef, attempt);
    try {
      const response = await request(
        attempt,
        authorization.metadata,
        projectedAction,
      );
      await refresh();
      attempts.delete(attemptRef);
      return { ok: true, data: response };
    } catch (err) {
      const shortage = parseShortage(httpError(err).data);
      if (shortage) return { ok: false, shortage };
      if (mutationGuard.handleMutationError(err)) return { ok: false };
      useSonner.error(httpErrorMessage(err, "Falha na ação. Tente de novo."));
      return { ok: false };
    } finally {
      const next = new Set(busy.value);
      next.delete(pk);
      busy.value = next;
    }
  }

  // O finish não vive mais aqui: fechar o lote é o Fechamento (quiosque de
  // QC, useQcKiosk), sempre com partição — ADR-017 §9.
  const voidOrder = (pk: number, rev: number, reason: string) =>
    post(pk, "void", (idempotencyKey, metadata) =>
      voidProductionWorkOrder(pk, {
        reason,
        expected_rev:
          kds.value?.actions.find((action) => action.ref === `void:${pk}`)
            ?.expected_rev ?? rev,
        ...metadata,
        idempotency_key: idempotencyKey,
      }),
    );

  const registerOldDough = (
    pk: number,
    rev: number,
    input: RegisterOldDoughInput,
  ) =>
    post<RegisterOldDoughResponse>(
      pk,
      "register_old_dough",
      (idempotencyKey, metadata, action) =>
        $fetch<RegisterOldDoughResponse>(action.href, {
          method: action.method,
          body: {
            quantity: input.quantity,
            unit: input.unit,
            expiry_date: input.expiryDate,
            position_ref: input.positionRef || undefined,
            note: input.note?.trim() || undefined,
            expected_rev: action.expected_rev ?? rev,
            ...metadata,
            idempotency_key: idempotencyKey,
          },
        }),
    );

  const authorizeFormulaDeviation = (
    pk: number,
    rev: number,
    input: AuthorizeFormulaDeviationInput,
  ) =>
    post<AuthorizeFormulaDeviationResponse>(
      pk,
      "authorize_formula_deviation",
      (idempotencyKey, metadata, action) =>
        $fetch<AuthorizeFormulaDeviationResponse>(action.href, {
          method: action.method,
          body: {
            ingredient_ref: input.ingredientRef,
            actual_quantity: input.actualQuantity,
            batch_ref: input.batchRef?.trim() || undefined,
            reason: input.reason.trim(),
            expected_rev: action.expected_rev ?? rev,
            ...metadata,
            idempotency_key: idempotencyKey,
          },
        }),
    );

  return {
    cards,
    totalCount,
    lateCount,
    pending,
    error,
    refresh,
    actionFor,
    isBusy,
    voidOrder,
    registerOldDough,
    authorizeFormulaDeviation,
  };
}
