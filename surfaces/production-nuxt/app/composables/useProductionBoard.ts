// Production planning read-side. Single source for the planning matrix:
//   - useFetch the production board projection (GET /api/v1/backstage/production/);
//   - SSE first (ADR-016): o canal `backstage-production` (BFF /sse/production)
//     avisa a cada lote planejado, aberto, ajustado ou fechado, e a tela refaz o
//     GET canônico. Antes ninguém ouvia o canal e o lote aberto no tablet do forno
//     levava até 60 s para aparecer no do planejamento (mapa de cenários, P2-18);
//   - o poll de 60 s fica só de reserva (stream caído, deploy).
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
import { newProductionMutationKey } from "~/utils/mutationKey";
import {
  useProductionMutationGuard,
  type ProductionMutationBlock,
  type ProductionMutationMetadata,
} from "~/composables/useProductionMutationGuard";
import {
  openResilientEventSource,
  type ResilientEventSource,
} from "../../../operator-kit/app/utils/resilientEventSource";

/** Eventos do canal `backstage-production` (shop/handlers/_sse_emitters.py). */
export const PRODUCTION_SSE_EVENTS = ["backstage-production-update"] as const;
/** Poll de reserva: a atualização normal chega pelo SSE. */
export const PRODUCTION_FALLBACK_POLL_MS = 60_000;

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

  useAdaptivePoll(refresh, () => PRODUCTION_FALLBACK_POLL_MS);

  // `realtime` diz HONESTAMENTE se a tela recebe push ou vive do poll de reserva.
  const config = useRuntimeConfig();
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let source: ResilientEventSource | null = null;
  // Um lote planejado em massa dispara uma rajada de avisos: uma releitura em voo
  // por vez, e o aviso que chega no meio garante uma releitura depois dela.
  let inFlight: Promise<unknown> | null = null;
  let queued = false;
  function refreshOnPush() {
    queued = true;
    if (inFlight) return;
    inFlight = (async () => {
      while (queued) {
        queued = false;
        await refresh();
      }
    })()
      .catch(() => {})
      .finally(() => {
        inFlight = null;
      });
  }

  function connectSse() {
    if (source) return;
    realtime.value = "connecting";
    source = openResilientEventSource({
      url: ssePath("/sse/production", config.app.baseURL),
      events: PRODUCTION_SSE_EVENTS,
      onEvent: refreshOnPush,
      onOpen: (reconnected) => {
        realtime.value = "live";
        // Reabriu depois de uma queda: cobre o que passou no meio.
        if (reconnected) refreshOnPush();
      },
      onDown: () => {
        realtime.value = "polling";
      },
    });
  }

  // Conecta depois da primeira leitura boa (sessão e permissão provadas): sem ela
  // o canal seria recusado e o stream ficaria tentando à toa.
  let stopWaitingForRead: (() => void) | undefined;
  onMounted(() => {
    if (!pending.value && !error.value) {
      connectSse();
      return;
    }
    stopWaitingForRead = watch([pending, error], ([p, e]) => {
      if (p || e) return;
      stopWaitingForRead?.();
      stopWaitingForRead = undefined;
      connectSse();
    });
  });
  onBeforeUnmount(() => {
    stopWaitingForRead?.();
    source?.close();
    source = null;
  });

  // a planning POST keys on the output_sku row (one in-flight per row).
  const busy = ref<Set<string>>(new Set());
  const attempts = new Map<string, string>();
  const isBusy = (key: string) => busy.value.has(key);

  async function post(
    key: string,
    actionRef: string,
    seenRev: number | null,
    action: (
      idempotencyKey: string,
      metadata: ProductionMutationMetadata,
      expectedRev: number | null,
    ) => Promise<unknown>,
  ): Promise<BoardActResult> {
    if (busy.value.has(key)) return { ok: false };
    busy.value = new Set(busy.value).add(key);
    try {
      return await authorizedPost(key, actionRef, seenRev, action);
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  async function authorizedPost(
    key: string,
    actionRef: string,
    seenRev: number | null,
    action: (
      idempotencyKey: string,
      metadata: ProductionMutationMetadata,
      expectedRev: number | null,
    ) => Promise<unknown>,
  ): Promise<BoardActResult> {
    const authorization = await mutationGuard.authorizeFreshMutation(
      actionRef,
      seenRev,
    );
    if (!authorization.ok) return { ok: false, blocked: authorization.blocked };
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
    }
  }

  // ⚠️ `expected_rev` é a revisão que ESTE quadro leu, e é o que impede duas bancadas
  // de se sobrescreverem. A bancada A ajusta para 40 enquanto a B ajusta para 25 sobre
  // um quadro de sessenta segundos de idade: sem o número, o último POST vence, sem 409
  // e sem aviso. Com ele, a segunda recebe "a fornada mudou em outra tela".
  //
  // ⚠️ O POST manda a revisão da PROJEÇÃO atual (é ela que a prova assina), e o
  // poll troca a projeção por baixo do diálogo aberto. Sem comparar com a revisão
  // que o diálogo mostrou (`payload.expected_rev`), o poll "adotava" a mudança da
  // outra bancada e o último POST voltava a vencer em silêncio.
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
    // A revisão que o operador viu no diálogo; a do POST vem da projeção
    // assinada, e as duas têm que bater (ver `authorizeFreshMutation`).
    const seenRev = payload.work_order_id ? (payload.expected_rev ?? null) : null;
    return post(key, actionRef, seenRev, (idempotencyKey, metadata, expectedRev) =>
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
    return post(key, `start:${woPk}`, rev, (idempotencyKey, metadata, expectedRev) =>
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
    realtime,
    isBusy,
    plan,
    start,
  };
}
