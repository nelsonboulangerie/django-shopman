<script setup lang="ts">
// A GRADE por etapa — um motor, três lentes (refinos Pablo 2026-07-03):
//   PRODUTO | leitura | AÇÃO — cada lente tem UMA coluna de leitura e UMA de
//   ação com verbo no cabeçalho:
//   · plan (Planejamento): SUGERIDO  | PLANEJADO  (todos os SKUs);
//   · open (Abertura):     PLANEJADO | PREVISTO   (só linhas com número).
// O fechamento (PREVISTO → REALIZADO) mora na página /close, no quiosque de QC.
// A ação abre overlay com quantidade em stepper touch (+/−) e confirmação
// explícita; cada informe vira evento imutável (actor + timestamp → BI).
// Na Abertura a ação é UMA só: "Confirmar" (o mesmo verbo do Planejamento)
// diz o previsto, que segue para o Fechamento, já preenchido com o planejado
// (decisão Pablo 2026-09-16); o número fica na coluna Planejado, não no botão.
// A diferença para o planejado é rendimento da massa, não perda: fica nos dois
// números da ordem, sem pedir motivo; motivo se pede no Fechamento, onde há
// produto pronto que pode sumir. Sem "iniciar", sem subetapas, sem máquina de
// estados: fermentação e afins são ferramenta (timer), nunca fluxo.
// Instruções específicas do SKU (peso de corte etc.) terão casa neste overlay
// (estudo de notação de pâtonnage pendente). Nomenclatura interna do sistema
// intacta (planned/started/finished) — as lentes são linguagem de UI.
import { nextTick, onMounted } from "vue";

import {
  boardDisplay,
  commitmentChipLabel,
  dayContextLine,
  formatQty,
  formatQtyUnit,
  fullDateLabel,
  latestPlanTime,
  plannedAsSuggested,
  isoForOffset,
  isStale,
  matchesRowQuery,
  rowCommitments,
  rowCommittedUnits,
  rowLabel,
} from "~/presentation/production";
import { suggestionSignal } from "~/presentation/planningReason";
import {
  cleanPreview,
  openRowGroups,
  openRowPending,
  planRowGroups,
  type OpenFilter,
  type PlanFilter,
} from "~/presentation/planningRows";
import {
  periodAnchor,
  periodOfDay,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";
import {
  moreMenuGroups,
  type OperatorMoreMenuItem,
} from "../../../operator-kit/app/presentation/moreMenu";
import type {
  ProductionMatrixRowProjection,
  ProductionShortageError,
  WorkOrderCardProjection,
} from "~/types/production";
import { defaultPlanningDate } from "~/composables/useProductionBoard";

const props = defineProps<{
  stage: "plan" | "open";
  title: string;
}>();

const route = useRoute();
const routeDate = typeof route.query.date === "string" ? route.query.date : "";

// A Produção abre em HOJE (o lote é do dia); só o Planejamento abre no dia
// seguinte à tarde, quando o padeiro planeja a próxima leva. Sem isto, a grade
// herdava o default de planejamento e "Produção" amanhecia em amanhã depois do
// meio-dia.
const {
  board,
  rows,
  selectedDate,
  pending,
  error,
  refresh,
  isBusy,
  plan,
  start,
} = useProductionBoard(
  routeDate ||
    (props.stage === "plan" ? defaultPlanningDate() : isoForOffset(0)),
);
const kds = useProductionKds();

const access = computed(() => board.value?.access ?? null);

const query = ref(typeof route.query.q === "string" ? route.query.q : "");
watch(
  () => route.query.q,
  (q) => {
    if (typeof q === "string") query.value = q;
  },
);
watch(
  () => route.query.date,
  (value) => {
    if (typeof value === "string") selectedDate.value = value;
  },
);

// ── Data: o "Período" do kit em Dia (Tipo 2), com ‹ › que andam um dia ─────
const todayISO = isoForOffset(0);
const period = computed<PeriodSelection>({
  get: () => periodOfDay("day", selectedDate.value, todayISO),
  set: (next) => {
    selectedDate.value = periodAnchor(next, todayISO);
  },
});
// ── Filtro por ficha-base (higiene visual por grupo de massa) ───────────────
const baseFilter = ref("");
const baseOptions = computed(() => board.value?.base_recipes ?? []);
// O `NuxtSelect` não aceita valor vazio num item: "todas" tem valor próprio.
const ALL_BASES = "__all__";
const baseItems = computed(() => [
  { value: ALL_BASES, label: "Todas as bases" },
  ...baseOptions.value.map((base) => ({
    value: base.output_sku,
    label: `${base.name} (${base.count})`,
  })),
]);
const baseModel = computed({
  get: () => baseFilter.value || ALL_BASES,
  set: (value: string) => {
    baseFilter.value = value === ALL_BASES ? "" : value;
  },
});

// ── Papéis de coluna por lente (cruzados com a permissão) ───────────────────
const lens = computed(() => {
  if (props.stage === "plan") {
    return {
      read: {
        key: "suggested",
        label: "Sugerido",
        visible: !!access.value?.can_view_suggested,
      },
      action: {
        key: "planned",
        label: "Planejado",
        visible: !!access.value?.can_view_planned,
        editable: Boolean(
          access.value?.can_edit_planned || access.value?.can_edit_suggested,
        ),
      },
    } as const;
  }
  return {
    read: {
      key: "planned",
      label: "Planejado",
      visible: !!access.value?.can_view_planned,
    },
    action: {
      key: "started",
      label: "Previsto",
      visible: !!access.value?.can_view_started,
      editable: !!access.value?.can_edit_started,
    },
  } as const;
});

// Linhas por lente: Planejamento vê TODOS os SKUs; Abertura só quem tem
// número relevante (higiene de foco na bancada).
const stageRows = computed<ProductionMatrixRowProjection[]>(() => {
  let base = rows.value.filter((r) => matchesRowQuery(r, query.value));
  if (baseFilter.value) {
    base = base.filter((r) =>
      r.base_usages.some((usage) => usage.output_sku === baseFilter.value),
    );
  }
  if (props.stage === "open") {
    return base.filter((r) => r.planned_qty !== "0" || r.started_qty !== "0");
  }
  return base;
});

// Board tolerante a dado velho: só troca a grade por carregando/erro quando NÃO há
// dado; havendo dado, mostra-o sempre + chip de degradação honesto se a última
// atualização falhou (dado velho visível > quadro vazio).
const display = computed(() =>
  boardDisplay({
    pending: pending.value,
    error: !!error.value,
    hasData: rows.value.length > 0,
  }),
);
const stale = computed(() =>
  isStale({ error: !!error.value, hasData: rows.value.length > 0 }),
);

// Planejamento vazio é falta de receita ativa: o aviso leva ao livro de receitas,
// onde se ativa ou cria uma. Quem não vê as receitas sabe a quem pedir.
const recipeBook = useRecipeBookAccess();

// ── Overlays ────────────────────────────────────────────────────────────────
// O "Por quê" abre ancorado na linha (um por vez); a linha fica marcada
// enquanto ele está aberto.
const reasonSku = ref<string | null>(null);
const reasonTriggers = new Map<string, HTMLElement>();
const planRow = ref<ProductionMatrixRowProjection | null>(null);
const planQty = ref("");
// Os campos de quantidade são `NuxtInput`: o foco vai ao `<input>` que ele expõe.
type QtyField = { inputRef?: HTMLInputElement | null } | null;
const planQtyInput = ref<QtyField>(null);
const planSubmitting = ref(false);
const planSource = ref<"manual" | "suggested">("manual");
const selectedPlannedPk = ref<number | null>(null);

// O gesto de planejar tem TRÊS sentidos, e o operador precisa saber qual está
// fazendo (o kernel já distingue: set_planned_quantity ajusta a WO planejada;
// depois do start ela sai do "planejado" e um novo plano cria OUTRO lote):
//   · plan      — nada na data ainda: planeja a primeira quantidade;
//   · adjust    — existe WO planejada: SUBSTITUI a quantidade (0 remove);
//   · new-batch — a produção já assumiu (aberto/fechado): cria lote que
//                 SOMA ao dia — explícito, nunca silencioso.
type PlanMode = "plan" | "adjust" | "new-batch";
const planMode = computed<PlanMode>(() => {
  const row = planRow.value;
  if (!row) return "plan";
  if (row.planned_qty !== "0") return "adjust";
  if (row.started_qty !== "0" || row.finished_qty !== "0") return "new-batch";
  return "plan";
});
function rowPlanMode(row: ProductionMatrixRowProjection): PlanMode {
  if (row.planned_qty !== "0") return "adjust";
  if (row.started_qty !== "0" || row.finished_qty !== "0") return "new-batch";
  return "plan";
}
const PLAN_TITLE: Record<PlanMode, string> = {
  plan: "Planejar",
  adjust: "Ajustar planejado",
  "new-batch": "Planejar novo lote",
};
const startRow = ref<ProductionMatrixRowProjection | null>(null);
const startQty = ref("");
const startQtyInput = ref<QtyField>(null);
function focusQty(field: typeof planQtyInput) {
  void nextTick(() => field.value?.inputRef?.focus());
}
const startSubmitting = ref(false);
const selectedStartPk = ref<number | null>(null);
const startedRow = ref<ProductionMatrixRowProjection | null>(null);
const selectedStartedPk = ref<number | null>(null);
const voidReason = ref("");
const voidConfirming = ref(false);
const commitmentsRow = ref<ProductionMatrixRowProjection | null>(null);
const shortage = ref<ProductionShortageError | null>(null);
// De onde veio a recusa: "Revisar quantidade" devolve o operador ao diálogo que
// ele acabou de confirmar, com o número que digitou.
const lastStartAttempt = ref<{
  row: ProductionMatrixRowProjection;
  workOrderPk: number;
  quantity: string;
} | null>(null);
const lastPlanAttempt = ref<{
  key: string;
  payload: Parameters<typeof plan>[1];
  successMessage: string;
} | null>(null);

const commitmentsList = computed(() =>
  commitmentsRow.value ? rowCommitments(commitmentsRow.value) : [],
);

const selectedPlannedOrder = computed<WorkOrderCardProjection | null>(
  () =>
    planRow.value?.planned_orders.find(
      (candidate) => candidate.pk === selectedPlannedPk.value,
    ) ?? null,
);

const selectedStartOrder = computed<WorkOrderCardProjection | null>(
  () =>
    startRow.value?.planned_orders.find(
      (candidate) => candidate.pk === selectedStartPk.value,
    ) ?? null,
);

const startedDialogOrders = computed<WorkOrderCardProjection[]>(() => {
  const row = startedRow.value;
  if (!row) return [];
  return row.started_orders.length ? row.started_orders : row.planned_orders;
});
const selectedStartedOrder = computed<WorkOrderCardProjection | null>(
  () =>
    startedDialogOrders.value.find(
      (candidate) => candidate.pk === selectedStartedPk.value,
    ) ?? null,
);

// Diferente do planejado? A tela diz, mas não pergunta: rendimento da massa
// é número, e os dois números ficam na ordem.
function qtyNumber(value: string): number {
  return parseFloat(value.replace(",", ".")) || 0;
}
const startDiverges = computed(() => {
  const wo = selectedStartOrder.value;
  if (!wo) return false;
  return qtyNumber(startQty.value) !== qtyNumber(wo.planned_qty);
});
const startReady = computed(
  () => !!selectedStartOrder.value && qtyNumber(startQty.value) > 0,
);

// Stepper touch: quantidade sempre editável com +/− generosos.
// (Recebe o NOME do campo — no template o Vue desembrulha refs, então passar
// `planQty` entregaria a string, não o ref.)
const qtyFields = {
  plan: planQty,
  start: startQty,
} as const;
function bump(field: keyof typeof qtyFields, delta: number) {
  const target = qtyFields[field];
  const current = parseFloat(target.value.replace(",", ".")) || 0;
  const next = Math.max(0, current + delta);
  target.value = Number.isInteger(next)
    ? String(next)
    : next.toFixed(3).replace(/\.?0+$/, "");
}

function openPlan(
  row: ProductionMatrixRowProjection,
  requestedSource?: "manual" | "suggested",
) {
  const source =
    requestedSource ??
    (access.value?.can_edit_planned ? "manual" : "suggested");
  if (source === "suggested" && !row.suggestion) return;
  planSource.value = source;
  planRow.value = row;
  selectedPlannedPk.value =
    row.planned_orders.length === 1 ? row.planned_orders[0]!.pk : null;
  const mode = rowPlanMode(row);
  // Novo lote parte de 0 — a sugestão era para o dia inteiro e a produção já
  // assumiu parte dela; pré-preencher aqui dobraria o dia sem querer.
  if (source === "suggested") planQty.value = row.suggestion?.quantity ?? "";
  else if (mode === "new-batch") planQty.value = "0";
  else if (mode === "adjust")
    planQty.value = selectedPlannedOrder.value?.planned_qty ?? "";
  else planQty.value = row.suggestion?.quantity ?? "0";
  if (!row.planned_orders.length || selectedPlannedPk.value != null) {
    focusQty(planQtyInput);
  }
}

function selectPlannedWorkOrder(workOrder: WorkOrderCardProjection) {
  selectedPlannedPk.value = workOrder.pk;
  if (planSource.value === "manual") planQty.value = workOrder.planned_qty;
  focusQty(planQtyInput);
}

function toggleReason(row: ProductionMatrixRowProjection) {
  reasonSku.value = reasonSku.value === row.output_sku ? null : row.output_sku;
}

function closeReason(outputSku: string) {
  if (reasonSku.value === outputSku) reasonSku.value = null;
}

function rememberReasonTrigger(outputSku: string, el: unknown) {
  // O "Por quê" é um `NuxtButton`: o elemento focável é o `$el` dele.
  const node =
    el instanceof HTMLElement ? el : (el as { $el?: unknown } | null)?.$el;
  if (node instanceof HTMLElement) reasonTriggers.set(outputSku, node);
  else reasonTriggers.delete(outputSku);
}

// O toque no próprio "Por quê" é o gesto de alternar: sem isto o popover
// fecharia no pointerdown (fora do conteúdo) e o clique o reabriria.
function onReasonOutside(event: Event) {
  const target = event.target;
  if (
    target instanceof Element &&
    target.closest("[data-plan-reason-trigger]")
  ) {
    event.preventDefault();
  }
}

// Ao fechar (Esc, Fechar, fora), o foco volta ao "Por quê" da linha. Se o
// fechamento foi para planejar, o foco é do diálogo de planejamento.
function returnReasonFocus(event: Event, outputSku: string) {
  const trigger = reasonTriggers.get(outputSku);
  if (!trigger) return;
  event.preventDefault();
  if (planRow.value == null) trigger.focus();
}

// Do "Por quê" direto para o planejamento da linha: a sugestão como está, ou a
// alternativa que cabe no estoque (número próprio, então manual).
function planFromReason(
  row: ProductionMatrixRowProjection,
  quantity: string,
  source: "manual" | "suggested",
) {
  reasonSku.value = null;
  openPlan(row, source);
  if (planRow.value === row) planQty.value = quantity;
}

async function confirmPlan() {
  if (planSubmitting.value) return;
  const row = planRow.value;
  if (!row || row.recipe_pk == null || !board.value || !planQty.value.trim())
    return;
  if (row.planned_orders.length > 0 && !selectedPlannedOrder.value) return;
  planSubmitting.value = true;
  try {
    const res = await submitPlan(row, {
      quantity: planQty.value.trim(),
      source: planSource.value,
      workOrder: selectedPlannedOrder.value,
      newBatch: planMode.value === "new-batch",
    });
    if (res?.ok) {
      planRow.value = null;
      selectedPlannedPk.value = null;
    } else if (res?.shortage) {
      planRow.value = null;
    } else if (res?.blocked && res.blocked.code !== "offline") {
      resyncPlanDialog(row.output_sku);
    }
  } finally {
    planSubmitting.value = false;
  }
}

// O gesto de planejar, um só para o diálogo, a linha ("Planejar 52") e o conjunto
// ("Planejar os 16 como sugerido"): mesma posição, mesma origem, mesma recusa.
async function submitPlan(
  row: ProductionMatrixRowProjection,
  opts: {
    quantity: string;
    source: "manual" | "suggested";
    workOrder?: WorkOrderCardProjection | null;
    newBatch?: boolean;
    quiet?: boolean;
  },
) {
  if (row.recipe_pk == null || !board.value) return null;
  const positionRef =
    opts.workOrder?.position_ref ||
    board.value.selected_position_ref ||
    board.value.positions.find(
      (position) => position.pk === board.value?.default_position_pk,
    )?.ref ||
    board.value.positions.find((position) => position.is_default)?.ref;
  if (!positionRef) {
    useSonner.error("Configure uma posição padrão antes de planejar.");
    return null;
  }
  const payload: Parameters<typeof plan>[1] = {
    recipe_id: row.recipe_pk,
    work_order_id: opts.workOrder?.pk,
    quantity: opts.quantity,
    target_date: board.value.selected_date,
    expected_rev: opts.workOrder?.rev ?? null,
    position_ref: positionRef,
    source: opts.source,
  };
  const label = opts.newBatch ? "Novo lote planejado" : "Planejado";
  const successMessage = `${label}: ${rowLabel(row)} × ${opts.quantity}`;
  lastPlanAttempt.value = { key: row.output_sku, payload, successMessage };
  const res = await plan(row.output_sku, payload);
  if (res.ok) {
    lastPlanAttempt.value = null;
    drafts.delete(row.output_sku);
    if (!opts.quiet) useSonner.success(successMessage);
  } else if (res.shortage) {
    lastStartAttempt.value = null;
    shortage.value = res.shortage;
  }
  return res;
}

// Recusa por números que mudaram: o diálogo passa a mostrar a linha atual e
// mantém a quantidade que o operador digitou — ele confere e confirma de novo,
// sem redigitar.
function resyncPlanDialog(outputSku: string) {
  const fresh = rows.value.find((r) => r.output_sku === outputSku);
  if (!fresh || planRow.value?.output_sku !== outputSku) return;
  const typed = planQty.value;
  const chosen = selectedPlannedPk.value;
  planRow.value = fresh;
  selectedPlannedPk.value = fresh.planned_orders.some((o) => o.pk === chosen)
    ? chosen
    : fresh.planned_orders.length === 1
      ? fresh.planned_orders[0]!.pk
      : null;
  planQty.value = typed;
}

function resyncStartDialog(outputSku: string) {
  const fresh = rows.value.find((r) => r.output_sku === outputSku);
  if (!fresh || startRow.value?.output_sku !== outputSku) return;
  const typed = startQty.value;
  const chosen = selectedStartPk.value;
  startRow.value = fresh;
  selectedStartPk.value = fresh.planned_orders.some((o) => o.pk === chosen)
    ? chosen
    : fresh.planned_orders.length === 1
      ? fresh.planned_orders[0]!.pk
      : null;
  startQty.value = typed;
}

async function retryPlanWithForce(reason: string, overrideProof: string) {
  const attempt = lastPlanAttempt.value;
  if (!attempt) return;
  shortage.value = null;
  const result = await plan(attempt.key, {
    ...attempt.payload,
    force: true,
    reason,
    override_proof: overrideProof,
  });
  if (result.ok) {
    useSonner.success(attempt.successMessage);
    lastPlanAttempt.value = null;
  } else if (result.shortage) {
    shortage.value = result.shortage;
  }
}

function openStart(row: ProductionMatrixRowProjection) {
  startRow.value = row;
  selectedStartPk.value =
    row.planned_orders.length === 1 ? row.planned_orders[0]!.pk : null;
  startQty.value = selectedStartOrder.value?.planned_qty ?? "";
  if (selectedStartPk.value != null) {
    focusQty(startQtyInput);
  }
}

function selectStartWorkOrder(workOrder: WorkOrderCardProjection) {
  selectedStartPk.value = workOrder.pk;
  startQty.value = workOrder.planned_qty;
  focusQty(startQtyInput);
}

async function confirmStart() {
  if (startSubmitting.value) return;
  const row = startRow.value;
  const wo = selectedStartOrder.value;
  if (!row || !wo || !startReady.value) return;
  startSubmitting.value = true;
  try {
    const res = await start(
      row.output_sku,
      wo.pk,
      wo.rev,
      startQty.value.trim(),
    );
    if (res.ok) {
      startRow.value = null;
      selectedStartPk.value = null;
      kds.refresh();
      useSonner.success(
        `Lote aberto: ${rowLabel(row)} × ${startQty.value.trim()}`,
      );
    } else if (res.shortage) {
      // Confirmar abaixo das encomendas nunca é forçável (o servidor não
      // oferece "force" aqui): a recusa diz quanto falta e devolve o número.
      lastStartAttempt.value = {
        row,
        workOrderPk: wo.pk,
        quantity: startQty.value.trim(),
      };
      lastPlanAttempt.value = null;
      startRow.value = null;
      selectedStartPk.value = null;
      shortage.value = res.shortage;
    } else if (res.blocked && res.blocked.code !== "offline") {
      resyncStartDialog(row.output_sku);
    }
  } finally {
    startSubmitting.value = false;
  }
}

// "Revisar quantidade": volta ao diálogo de onde a recusa veio, com a linha
// atual do quadro e o número que o operador digitou.
function reviewShortage() {
  shortage.value = null;
  const startAttempt = lastStartAttempt.value;
  if (startAttempt) {
    lastStartAttempt.value = null;
    const fresh =
      rows.value.find((r) => r.output_sku === startAttempt.row.output_sku) ??
      startAttempt.row;
    startRow.value = fresh;
    selectedStartPk.value = fresh.planned_orders.some(
      (o) => o.pk === startAttempt.workOrderPk,
    )
      ? startAttempt.workOrderPk
      : null;
    startQty.value = startAttempt.quantity;
    focusQty(startQtyInput);
    return;
  }
  const planAttempt = lastPlanAttempt.value;
  const row = planAttempt
    ? rows.value.find((r) => r.output_sku === planAttempt.key)
    : null;
  if (!planAttempt || !row) return;
  planSource.value = planAttempt.payload.source ?? "manual";
  planRow.value = row;
  selectedPlannedPk.value = row.planned_orders.some(
    (o) => o.pk === planAttempt.payload.work_order_id,
  )
    ? (planAttempt.payload.work_order_id ?? null)
    : row.planned_orders.length === 1
      ? row.planned_orders[0]!.pk
      : null;
  planQty.value = String(planAttempt.payload.quantity);
  focusQty(planQtyInput);
}

function closeShortage() {
  shortage.value = null;
  lastStartAttempt.value = null;
}

// O lote já aberto abre só para conferência e cancelamento, nada de gerir
// etapa por aqui (a decisão de 16/09 tirou a máquina de estados da bancada).
function openStarted(row: ProductionMatrixRowProjection) {
  startedRow.value = row;
  selectedStartedPk.value =
    row.started_orders.length === 1 ? row.started_orders[0]!.pk : null;
  voidConfirming.value = false;
  kds.refresh();
}

async function confirmVoid() {
  const row = startedRow.value;
  const wo = selectedStartedOrder.value;
  if (!row || !wo) return;
  const res = await kds.voidOrder(
    wo.pk,
    wo.rev,
    voidReason.value.trim() || "Cancelado pelo operador",
  );
  if (res.ok) {
    startedRow.value = null;
    voidConfirming.value = false;
    voidReason.value = "";
    refresh();
    useSonner.success(`Lote cancelado: ${rowLabel(row)}`);
  }
}

// ── ⋯ da linha aberta (R12) e "pressione e segure" no tablet deitado (R13) ──
// As ações da linha são DADOS, uma fonte só: o ⋯ (`OperatorMoreMenu`) e o menu de
// contexto da linha (`NuxtContextMenu`, que abre ao segurar a linha no toque e no
// clique direito no mouse) desenham a mesma lista.
function openRowMenu(row: ProductionMatrixRowProjection): OperatorMoreMenuItem[][] {
  const main: OperatorMoreMenuItem[] = [{ type: "label", label: rowLabel(row) }];
  if (row.started_orders.length)
    main.push({
      label: "Ver lançamento",
      icon: "i-lucide-receipt-text",
      onSelect: () => openStarted(row),
    });
  if (row.planned_orders.length && actionEnabled(row))
    main.push({
      label: "Confirmar previsto",
      icon: "i-lucide-check",
      onSelect: () => openStart(row),
    });
  if (rowCommittedUnits(row) > 0)
    main.push({
      label: `Ver encomendas (${rowCommittedUnits(row)} un.)`,
      icon: "i-lucide-shopping-bag",
      onSelect: () => {
        commitmentsRow.value = row;
      },
    });
  const groups = [main];
  if (rowVoidable(row))
    groups.push([
      {
        label: "Cancelar lote…",
        icon: "i-lucide-undo-2",
        color: "error",
        onSelect: () => openVoid(row),
      },
    ]);
  return groups;
}
function rowVoidable(row: ProductionMatrixRowProjection): boolean {
  return [...row.started_orders, ...row.planned_orders].some((order) => order.can_void);
}
// "Cancelar lote…" direto do menu: o diálogo do lote abre já na confirmação.
function openVoid(row: ProductionMatrixRowProjection) {
  startedRow.value = row;
  const orders = voidableOrders(row);
  selectedStartedPk.value = orders.length === 1 ? orders[0]!.pk : null;
  voidConfirming.value = true;
}
function voidableOrders(row: ProductionMatrixRowProjection): WorkOrderCardProjection[] {
  const started = row.started_orders.filter((order) => order.can_void);
  return started.length ? started : row.planned_orders.filter((order) => order.can_void);
}

// Tablet deitado (toque, 1024 px ou mais): "Confirmar" abre o painel encaixado à
// direita, sem cobrir a lista (v3 `depois-producao-dia-tablet`).
// Só depois de montar: o SSR não conhece a tela, e a hidratação não corrige
// classe divergente (o botão nasceria cheio e ficaria cheio).
const touchPointer = useTouchPointer();
const screen = useScreen();
const gridMounted = ref(false);
onMounted(() => {
  gridMounted.value = true;
});
const docked = computed(
  () => gridMounted.value && touchPointer.value && !screen.belowLg.value,
);
// Com o painel encaixado a lista estreita: colunas de número compactas (v3 tablet).
const openCols = computed(() =>
  docked.value
    ? "lg:grid-cols-[minmax(0,1fr)_118px_60px_72px_auto] lg:gap-x-3"
    : "lg:grid-cols-[minmax(0,1fr)_140px_110px_110px_236px]",
);
const startPadFresh = ref(true);
function startDigit(digit: string) {
  const next = startPadFresh.value ? digit : `${startQty.value}${digit}`;
  startQty.value = String(Math.min(99999, Number(next) || 0));
  startPadFresh.value = false;
}
function startBackspace() {
  startQty.value = startQty.value.length <= 1 ? "0" : startQty.value.slice(0, -1);
  startPadFresh.value = false;
}
function startClear() {
  startQty.value = "0";
  startPadFresh.value = true;
}
watch(startRow, () => {
  startPadFresh.value = true;
});

function onAction(row: ProductionMatrixRowProjection) {
  if (props.stage === "plan") return openPlan(row);
  if (row.planned_orders.length) return openStart(row);
  if (row.started_orders.length) return openStarted(row);
}

function actionEnabled(row: ProductionMatrixRowProjection): boolean {
  if (!lens.value.action.editable) return false;
  if (props.stage === "plan") {
    return Boolean(
      row.recipe_pk != null &&
      (access.value?.can_edit_planned ||
        (row.suggestion && access.value?.can_edit_suggested)),
    );
  }
  return !!row.started_orders.length || row.planned_orders.length > 0;
}

const planQtyValid = computed(() => {
  const qty = parseFloat(planQty.value.replace(",", "."));
  if (Number.isNaN(qty) || qty < 0) return false;
  // Zerar só faz sentido quando há planejado a remover; num lote novo, 0 é no-op.
  if (qty === 0) return planMode.value === "adjust";
  return true;
});
const planActionAllowed = computed(() =>
  planSource.value === "suggested"
    ? access.value?.can_edit_suggested === true
    : access.value?.can_edit_planned === true,
);

function cellQty(value: string): string {
  return value === "0" ? "—" : value;
}

// Progresso do dia, no cabeçalho: "4 de 28 planejados" (Planejamento) ou "5 de 8
// abertos" (Abertura), com a barra do quanto o dia andou. Conta produtos (linhas),
// como a prévia v4: o número e a barra falam da mesma coisa.
const headerCount = computed(() => {
  if (props.stage === "plan") {
    const { done, all } = planGroups.value.counts;
    return {
      count: done,
      total: all,
      label: "planejados",
      pct: all ? Math.round((done / all) * 100) : null,
    };
  }
  const { opened, all } = openGroups.value.counts;
  return {
    count: opened,
    total: all,
    label: "abertos",
    pct: all ? Math.round((opened / all) * 100) : null,
  };
});

// ── V4: a linha decide (stepper + "Planejar N"), o conjunto e os planejados ────
// Prévia v4 `plano-porque4.html`: uma primária por linha com o número; o stepper na
// linha; mudou, a sugestão mostra "você mudou de 30 · voltar". O diálogo continua para
// o que pede escolha (ajustar um lote planejado, somar um lote novo, a recusa).
const planFilter = ref<PlanFilter>("all");
const openFilter = ref<OpenFilter>("all");
const expandClean = ref(false);
const expandManual = ref(false);
const drafts = reactive(new Map<string, string>());
const inlineSubmitting = ref<string | null>(null);
const bulkSubmitting = ref(false);

const planGroups = computed(() =>
  planRowGroups(stageRows.value, planFilter.value, {
    expandClean: expandClean.value,
    expandManual: expandManual.value,
    searching: !!query.value.trim(),
  }),
);
const openGroups = computed(() =>
  openRowGroups(stageRows.value, openFilter.value),
);
const visibleRowCount = computed(() =>
  props.stage === "plan"
    ? planGroups.value.focus.length +
      planGroups.value.clean.length +
      planGroups.value.manual.length +
      planGroups.value.planned.length
    : openGroups.value.rows.length,
);

const PLAN_FILTERS: Array<{ key: PlanFilter; label: string }> = [
  { key: "all", label: "Todos" },
  { key: "todo", label: "A planejar" },
  { key: "flagged", label: "Com ressalva" },
  { key: "done", label: "Planejados" },
];
const OPEN_FILTERS: Array<{ key: OpenFilter; label: string }> = [
  { key: "all", label: "Todos" },
  { key: "pending", label: "A confirmar" },
  { key: "opened", label: "Abertos" },
];
// Os recortes rápidos são abas em pílula com a contagem, como no Gestor.
const planFilterTabs = computed(() =>
  PLAN_FILTERS.map((filter) => ({
    value: filter.key,
    label: filter.label,
    count: planGroups.value.counts[filter.key],
  })),
);
const openFilterTabs = computed(() =>
  OPEN_FILTERS.map((filter) => ({
    value: filter.key,
    label: filter.label,
    count: openGroups.value.counts[filter.key],
  })),
);

/** A persona que só pode seguir a sugestão planeja o número exato dela. */
const inlineSource = computed<"manual" | "suggested">(() =>
  access.value?.can_edit_planned ? "manual" : "suggested",
);
const stepperEditable = computed(() => access.value?.can_edit_planned === true);

function draftOf(row: ProductionMatrixRowProjection): string {
  return drafts.get(row.output_sku) ?? row.suggestion?.quantity ?? "0";
}
function setDraft(row: ProductionMatrixRowProjection, value: string) {
  drafts.set(row.output_sku, value.replace(/[^\d.,]/g, ""));
}
function bumpDraft(row: ProductionMatrixRowProjection, delta: number) {
  const next = Math.max(0, qtyNumber(draftOf(row)) + delta);
  drafts.set(
    row.output_sku,
    Number.isInteger(next) ? String(next) : next.toFixed(3).replace(/\.?0+$/, ""),
  );
}
function draftChanged(row: ProductionMatrixRowProjection): boolean {
  return (
    !!row.suggestion &&
    drafts.has(row.output_sku) &&
    qtyNumber(draftOf(row)) !== qtyNumber(row.suggestion.quantity)
  );
}
function resetDraft(row: ProductionMatrixRowProjection) {
  drafts.delete(row.output_sku);
}
function inlineAllowed(row: ProductionMatrixRowProjection): boolean {
  if (!actionEnabled(row)) return false;
  if (qtyNumber(draftOf(row)) <= 0) return false;
  if (inlineSource.value === "suggested") {
    return (
      !!row.suggestion &&
      access.value?.can_edit_suggested === true &&
      qtyNumber(draftOf(row)) === qtyNumber(row.suggestion.quantity)
    );
  }
  return true;
}

/** Por que a linha não planeja agora, escrito no próprio botão ("" = pode). */
function inlineBlock(row: ProductionMatrixRowProjection): string {
  if (!actionEnabled(row)) return "Sem permissão";
  if (qtyNumber(draftOf(row)) <= 0) return "Sem quantidade";
  if (!inlineAllowed(row)) return "Só a sugestão";
  return "";
}

async function planInline(row: ProductionMatrixRowProjection) {
  if (inlineSubmitting.value || !inlineAllowed(row)) return;
  inlineSubmitting.value = row.output_sku;
  try {
    await submitPlan(row, {
      quantity: draftOf(row).trim(),
      source: inlineSource.value,
    });
  } finally {
    inlineSubmitting.value = null;
  }
}

// "Planejar os 16 como sugerido": um sim para o conjunto, um a um no servidor (cada
// plano é um evento próprio). Parou numa recusa? A recusa aparece e o resto espera.
async function planCleanSet() {
  if (bulkSubmitting.value) return;
  const targets = [...planGroups.value.clean];
  if (!targets.length) return;
  bulkSubmitting.value = true;
  let done = 0;
  try {
    for (const row of targets) {
      const res = await submitPlan(row, {
        quantity: row.suggestion!.quantity,
        source: inlineSource.value,
        quiet: true,
      });
      if (!res?.ok) break;
      done += 1;
    }
  } finally {
    bulkSubmitting.value = false;
  }
  if (done)
    useSonner.success(
      done === 1 ? "1 produto planejado como sugerido." : `${done} produtos planejados como sugerido.`,
    );
}
const canPlanCleanSet = computed(
  () =>
    planGroups.value.clean.length > 0 &&
    (inlineSource.value === "manual" || access.value?.can_edit_suggested === true),
);
const cleanSummary = computed(() =>
  cleanPreview(planGroups.value.clean, rowLabel),
);
const manualSummary = computed(() => {
  const names = planGroups.value.manual.map(rowLabel);
  const head = names.slice(0, 4).join(", ");
  return names.length > 4 ? `${head} e mais ${names.length - 4}` : head;
});

function plannedQtyLabel(row: ProductionMatrixRowProjection): string {
  if (row.planned_qty !== "0") return row.planned_qty;
  return row.started_qty !== "0" ? row.started_qty : row.finished_qty;
}
function plannedNote(row: ProductionMatrixRowProjection): string {
  const parts: string[] = [];
  if (row.started_qty !== "0") parts.push(`${row.started_qty} previstas`);
  if (row.finished_qty !== "0") parts.push(`${row.finished_qty} realizadas`);
  return parts.join(" · ");
}

const baseLabel = computed(
  () =>
    baseOptions.value.find((base) => base.output_sku === baseFilter.value)
      ?.name ?? "todas",
);
// Os recortes ativos: número no "Filtros" e chips removíveis no celular.
const activeFilters = computed(() => {
  const list: { key: string; label: string; remove: () => void }[] = [];
  const quick =
    props.stage === "plan"
      ? PLAN_FILTERS.find((f) => f.key === planFilter.value && f.key !== "all")
      : OPEN_FILTERS.find((f) => f.key === openFilter.value && f.key !== "all");
  if (quick)
    list.push({
      key: "state",
      label: quick.label,
      remove: () => {
        planFilter.value = "all";
        openFilter.value = "all";
      },
    });
  if (baseFilter.value)
    list.push({
      key: "base",
      label: `Base: ${baseLabel.value}`,
      remove: () => {
        baseFilter.value = "";
      },
    });
  return list;
});
function plannedStateLabel(row: ProductionMatrixRowProjection): string {
  if (row.planned_qty !== "0") return "Planejado";
  return row.started_qty !== "0" ? "Aberto" : "Fechado";
}

const signalClass = {
  danger: "bg-destructive/10 text-destructive",
  warning: "bg-warning/15 text-warning",
} as const;

// "Sábado comum, sem feriado · previsão 24 °C e sol (como os sábados usados na conta)".
const dayLine = computed(() => {
  const sameWeekday = rows.value.some((row) => row.suggestion?.same_weekday);
  const weekday = weekdayPlural(selectedDate.value);
  return dayContextLine(
    board.value?.day_context ?? null,
    sameWeekday && weekday
      ? ["sábados", "domingos"].includes(weekday)
        ? `como os ${weekday} usados na conta`
        : `como as ${weekday} usadas na conta`
      : "",
  );
});
function weekdayPlural(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return "";
  const day = new Date(Date.UTC(+match[1]!, +match[2]! - 1, +match[3]!));
  return ["domingos", "segundas", "terças", "quartas", "quintas", "sextas", "sábados"][
    day.getUTCDay()
  ] ?? "";
}
// O ⋯ da linha dos planejados: o rótulo do grupo e um item por produto planejado.
const plannedLineMenu = computed(() => [
  { type: "label" as const, label: "Corrigir um planejado" },
  ...planGroups.value.planned.map((row) => ({
    label: `${rowLabel(row)} · ${formatQty(plannedQtyLabel(row), row.output_unit)}`,
    icon: "i-lucide-pencil",
    disabled: !actionEnabled(row) || isBusy(row.output_sku),
    onSelect: () => onAction(row),
  })),
]);
// Tocar num produto planejado: o estado dele e o que dá para fazer.
function plannedItemMenu(row: ProductionMatrixRowProjection) {
  const state = [
    `${plannedStateLabel(row)} ${formatQty(plannedQtyLabel(row), row.output_unit)}`,
    plannedNote(row),
    plannedAsSuggested(row) ? "como sugerido" : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const newBatch = rowPlanMode(row) === "new-batch";
  const items = [
    { type: "label" as const, label: rowLabel(row) },
    { type: "label" as const, label: state },
    {
      label: newBatch ? "Planejar novo lote" : "Corrigir quantidade",
      icon: newBatch ? "i-lucide-plus" : "i-lucide-pencil",
      disabled: !actionEnabled(row) || isBusy(row.output_sku),
      onSelect: () => onAction(row),
    },
  ];
  if (rowCommittedUnits(row) > 0)
    items.push({
      label: `Ver encomendas (${rowCommittedUnits(row)} un.)`,
      icon: "i-lucide-shopping-bag",
      disabled: false,
      onSelect: () => {
        commitmentsRow.value = row;
      },
    });
  return items;
}
// "Planejado 15:12": a hora do plano mais recente do dia.
const plannedTime = computed(() => latestPlanTime(planGroups.value.planned));
const allPlannedAsSuggested = computed(
  () =>
    planGroups.value.planned.length > 0 &&
    planGroups.value.planned.every(plannedAsSuggested),
);

// As descrições dos diálogos, como texto (o `NuxtModal` recebe uma frase).
const planDescription = computed(() => {
  const row = planRow.value;
  if (!row) return "";
  const parts = [row.output_sku, fullDateLabel(selectedDate.value)];
  if (row.suggestion) parts.push(`sugestão ${row.suggestion.quantity}`);
  return parts.join(" · ");
});
const startedDescription = computed(() => {
  const wo = selectedStartedOrder.value;
  const sku = startedRow.value?.output_sku ?? "";
  if (wo && wo.started_qty) {
    const launched = wo.started_at_display
      ? ` · lançado ${wo.started_at_display}`
      : "";
    return `#${wo.ref} · ${sku} · ${wo.started_qty} un. previstas seguem para o Fechamento${launched}`;
  }
  if (wo) return `#${wo.ref} · ${sku} · ${wo.planned_qty} un. planejadas`;
  return "Selecione o lote.";
});
</script>


<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <!-- Cabeçalho do kit: título, ao vivo, busca e o ⋯ na barra; na toolbar, o dia,
         os recortes e, no fim, "4 de 28 planejados" com a barra. -->
    <ProductionHeader
      v-model:query="query"
      :title="title"
      :active-filters="activeFilters"
      search-label="filtrando os produtos"
      :count="headerCount.count"
      :total="headerCount.total"
      :count-label="headerCount.label"
      :progress="headerCount.pct"
      :pending="pending"
      :stale="stale"
      @refresh="
        refresh();
        kds.refresh();
      "
    >
      <template #primary>
        <OperatorPeriodPicker
          v-model="period"
          compact
          class="[&_[data-period-today]]:hidden"
          :presets="['day']"
          :today="todayISO"
          label="Data"
          align="end"
        />
      </template>
      <template #filters>
        <!-- Os recortes rápidos: abas em pílula com a contagem, como no Gestor. -->
        <NuxtTabs
          v-if="stage === 'plan'"
          :model-value="planFilter"
          :items="planFilterTabs"
          :content="false"
          variant="pill"
          aria-label="Recorte do Planejamento"
          data-plan-filters
          @update:model-value="(value: string | number) => (planFilter = value as PlanFilter)"
       >
          <template #trailing="{ item }"><OperatorCountChip :count="item.count" /></template>
        </NuxtTabs>
        <NuxtTabs
          v-else
          :model-value="openFilter"
          :items="openFilterTabs"
          :content="false"
          variant="pill"
          aria-label="Recorte da Abertura"
          data-open-filters
          @update:model-value="(value: string | number) => (openFilter = value as OpenFilter)"
       >
          <template #trailing="{ item }"><OperatorCountChip :count="item.count" /></template>
        </NuxtTabs>
        <NuxtSelect
          v-if="baseOptions.length"
          v-model="baseModel"
          :items="baseItems"
          value-key="value"
          icon="i-lucide-layers"
          class="w-52"
          aria-label="Filtrar por ficha-base"
          data-base-filter
        />
        <!-- A ocasião e o clima do dia planejado, à direita dos recortes (v4 pino 8). -->
        <p
          v-if="stage === 'plan' && dayLine"
          class="ml-auto inline-flex min-w-0 items-center gap-1.5 op-label text-muted-foreground max-md:hidden"
          data-plan-day-context
        >
          <Icon name="lucide:sun" class="size-4 shrink-0" aria-hidden="true" />
          <span class="truncate">{{ dayLine }}</span>
        </p>
      </template>
    </ProductionHeader>

    <div class="flex min-h-0 flex-1">
    <section class="min-h-0 min-w-0 flex-1 overflow-auto px-3 pt-3 pb-4 md:px-4">
      <OperatorScreenState
        v-if="display === 'loading'"
        state="loading"
        what="o quadro"
      />

      <!-- Erro só toma a tela quando NÃO há dado nenhum a mostrar. -->
      <OperatorScreenState
        v-else-if="display === 'error'"
        state="error"
        what="o quadro"
        description="Estamos tentando reconectar sozinhos."
        @retry="refresh()"
      />

      <template v-else>
        <!-- Dado presente: chip de degradação honesto quando a última atualização falhou. -->
        <div
          v-if="stale"
          role="status"
          aria-live="polite"
          class="mb-3 inline-flex items-center gap-2 rounded-full border border-warning/40 bg-warning/10 px-3 py-2 op-label font-semibold text-warning"
        >
          <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
          <span>Sem atualizar: mostrando o último quadro carregado.</span>
        </div>

        <template v-if="!stageRows.length">
          <!-- Busca sem resultado: a frase do fim da seção diz isso. -->
          <template v-if="query.trim()" />
          <!-- Planejamento sem receita ativa: o aviso leva aonde se resolve. -->
          <NuxtAlert
            v-else-if="stage === 'plan'"
            color="warning"
            variant="subtle"
            icon="i-lucide-book-open"
            title="Nenhuma receita ativa."
            :description="
              recipeBook.canView.value
                ? 'O Planejamento sugere a partir das receitas ativas. Ative ou crie uma no livro de receitas.'
                : 'O Planejamento sugere a partir das receitas ativas. Peça a quem gerencia a produção para ativar ou criar uma receita.'
            "
            :ui="{ description: 'opacity-100' }"
            data-plan-empty
          >
            <template v-if="recipeBook.canView.value" #actions>
              <NuxtButton
                to="/recipes"
                color="warning"
                variant="solid"
                icon="i-lucide-book-open"
                label="Abrir as receitas"
                data-plan-empty-action
              />
            </template>
          </NuxtAlert>
          <OperatorScreenState
            v-else
            state="empty"
            icon="i-lucide-layout-grid"
            title="Nada planejado para produzir nesta data."
          >
            <template #actions>
              <NuxtButton
                to="/plan"
                color="neutral"
                variant="outline"
                label="Ir para o Planejamento"
              />
            </template>
          </OperatorScreenState>
        </template>

        <!-- ── Planejamento ─────────────────────────────────────────────────── -->
        <div
          v-else-if="stage === 'plan'"
          class="overflow-hidden rounded-lg border border-border bg-card"
          data-plan-table
        >
          <div
            class="hidden h-10 items-center gap-4 border-b border-border bg-muted/60 px-4 op-eyebrow text-muted-foreground lg:grid lg:grid-cols-[minmax(0,1fr)_250px_168px_176px]"
            aria-hidden="true"
          >
            <span>Produto</span>
            <span>{{ lens.read.visible ? "Sugestão" : "" }}</span>
            <span>{{ lens.action.visible ? "Quantidade" : "" }}</span>
            <span />
          </div>

          <div
            v-for="row in planGroups.focus"
            :key="row.output_sku"
            class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-4 py-3 last:border-b-0 lg:grid lg:h-[62px] lg:grid-cols-[minmax(0,1fr)_250px_168px_176px] lg:py-0"
            :class="
              reasonSku === row.output_sku
                ? 'bg-primary/5 shadow-[inset_0_0_0_2px_var(--primary)]'
                : ''
            "
            data-plan-row
            :data-sku="row.output_sku"
          >
            <!-- Produto: nome, SKU e o chip das encomendas. -->
            <div
              class="flex w-full min-w-0 items-center gap-2.5 lg:w-auto"
              data-row-product
            >
              <p class="min-w-0 truncate op-title">
                {{ rowLabel(row) }}
                <span class="font-mono op-micro font-normal text-muted-foreground">{{
                  row.output_sku
                }}</span>
              </p>
              <NuxtButton
                v-if="rowCommittedUnits(row) > 0"
                color="neutral"
                variant="ghost"
                icon="i-lucide-shopping-bag"
                class="shrink-0 tabular-nums"
                :ui="{ leadingIcon: 'text-info' }"
                :label="commitmentChipLabel(row)"
                :aria-label="`${commitmentChipLabel(row)}: unidades de ${rowLabel(row)} comprometidas com encomendas`"
                data-commitment-chip
                @click="commitmentsRow = row"
              />
            </div>

            <!-- Sugestão: o número e, no máximo, um sinal. A conta mora no "Por quê",
                 que abre ancorado na linha (UX-P2, L3). -->
            <div
              class="flex min-w-0 flex-1 items-center gap-2.5 max-sm:w-full max-sm:flex-none lg:flex-none"
            >
              <template v-if="lens.read.visible">
                <NuxtPopover
                  v-if="row.suggestion"
                  :open="reasonSku === row.output_sku"
                  :content="{
                    side: 'bottom',
                    align: 'end',
                    sideOffset: 6,
                    collisionPadding: 16,
                    onInteractOutside: onReasonOutside,
                    onCloseAutoFocus: (event: Event) =>
                      returnReasonFocus(event, row.output_sku),
                  }"
                  :ui="{
                    content: 'w-[33rem] max-w-[calc(100vw-2rem)] rounded-xl p-0',
                  }"
                  @update:open="
                    (open: boolean) => {
                      if (!open) closeReason(row.output_sku);
                    }
                  "
                >
                  <template #anchor>
                    <span class="flex min-w-0 flex-1 items-center gap-2.5">
                      <span
                        class="min-w-[30px] op-heading tnum"
                        :class="
                          draftChanged(row) || row.suggestion.quantity === '0'
                            ? 'text-muted-foreground'
                            : ''
                        "
                        >{{ formatQty(row.suggestion.quantity, row.output_unit) }}</span
                      >
                      <span
                        v-if="draftChanged(row)"
                        class="op-label leading-tight text-muted-foreground"
                        data-plan-changed
                      >
                        você mudou de {{ formatQty(row.suggestion.quantity, row.output_unit) }}<br />
                        <NuxtButton
                          color="primary"
                          variant="ghost"
                          class="-mx-2.5"
                          label="voltar"
                          @click="resetDraft(row)"
                        />
                      </span>
                      <span
                        v-else-if="suggestionSignal(row.suggestion)"
                        :class="[
                          'inline-flex h-[26px] shrink-0 items-center gap-[5px] whitespace-nowrap rounded-full px-[9px] op-label font-semibold',
                          signalClass[suggestionSignal(row.suggestion)!.tone],
                        ]"
                        data-testid="suggestion-signal"
                      >
                        <Icon
                          :name="suggestionSignal(row.suggestion)!.icon"
                          class="size-3.5"
                        />
                        {{ suggestionSignal(row.suggestion)!.label }}
                      </span>
                      <NuxtButton
                        :ref="(el) => rememberReasonTrigger(row.output_sku, el)"
                        color="neutral"
                        variant="ghost"
                        icon="i-lucide-info"
                        label="Por quê"
                        class="ml-auto shrink-0"
                        :active="reasonSku === row.output_sku"
                        active-color="primary"
                        active-variant="outline"
                        data-plan-reason-trigger
                        aria-haspopup="dialog"
                        :aria-expanded="reasonSku === row.output_sku"
                        :aria-label="`Por que ${row.suggestion.quantity} de ${rowLabel(row)}?`"
                        @click="toggleReason(row)"
                      />
                    </span>
                  </template>
                  <template #content>
                    <PlanReasonCard
                      v-if="reasonSku === row.output_sku"
                      :suggestion="row.suggestion"
                      :product-name="rowLabel(row)"
                      :iso-date="selectedDate"
                      :purchase-url="board?.purchase_url ?? ''"
                      :can-plan-suggested="!!access?.can_edit_suggested"
                      :can-plan-manual="!!access?.can_edit_planned"
                      @close="closeReason(row.output_sku)"
                      @plan="
                        (quantity, source) =>
                          planFromReason(row, quantity, source)
                      "
                    />
                  </template>
                </NuxtPopover>
                <span
                  v-else
                  class="op-label text-muted-foreground"
                  data-plan-no-suggestion
                  >sem sugestão para o dia</span
                >
              </template>
            </div>

            <!-- Quantidade: o stepper na linha; mudou, o campo fica em destaque e a
                 sugestão diz "você mudou". -->
            <template v-if="lens.action.visible">
              <div
                class="flex items-center gap-1 max-sm:min-w-[8.5rem] max-sm:flex-1"
              >
                <NuxtButton
                  icon="i-lucide-minus"
                  color="neutral"
                  variant="outline"
                  square
                  :disabled="!stepperEditable || !actionEnabled(row)"
                  :aria-label="`Diminuir ${rowLabel(row)}`"
                  @click="bumpDraft(row, -1)"
                />
                <NuxtInput
                  :model-value="draftOf(row)"
                  inputmode="decimal"
                  class="w-16 flex-1"
                  :color="draftChanged(row) ? 'primary' : 'neutral'"
                  :highlight="draftChanged(row)"
                  :ui="{ base: 'text-center tnum font-semibold' }"
                  :readonly="!stepperEditable || !actionEnabled(row)"
                  :aria-label="`Quantidade de ${rowLabel(row)}`"
                  @update:model-value="
                    (value: string | number) => setDraft(row, String(value))
                  "
                  @keydown.enter.prevent="planInline(row)"
                />
                <NuxtButton
                  icon="i-lucide-plus"
                  color="neutral"
                  variant="outline"
                  square
                  :disabled="!stepperEditable || !actionEnabled(row)"
                  :aria-label="`Aumentar ${rowLabel(row)}`"
                  @click="bumpDraft(row, 1)"
                />
              </div>
              <!-- Bloqueio antes do gesto (SPEC4 §3): sem quantidade ou sem permissão, o
                   botão fica tracejado com cadeado e o motivo escrito nele. -->
              <span
                v-if="inlineBlock(row)"
                class="inline-flex h-8 items-center justify-center gap-2 whitespace-nowrap rounded-md border border-dashed border-border px-4 op-label font-semibold text-muted-foreground max-sm:min-w-[8.5rem] max-sm:flex-1"
                data-plan-inline-blocked
              >
                <Icon name="lucide:lock" class="size-4" />
                {{ inlineBlock(row) }}
              </span>
              <NuxtButton
                v-else
                icon="i-lucide-check"
                class="justify-center max-sm:min-w-[8.5rem] max-sm:flex-1"
                :disabled="
                  isBusy(row.output_sku) ||
                  inlineSubmitting != null ||
                  bulkSubmitting
                "
                :aria-busy="inlineSubmitting === row.output_sku"
                :label="
                  inlineSubmitting === row.output_sku
                    ? 'Planejando…'
                    : `Planejar ${formatQty(draftOf(row), row.output_unit)}`
                "
                data-plan-inline
                @click="planInline(row)"
              />
            </template>
          </div>

          <!-- O que não tem ressalva vira conjunto: um "sim" para todos, ou ver um a um. -->
          <div
            v-if="planGroups.clean.length"
            class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-muted/40 px-4 py-3 last:border-b-0 lg:min-h-16"
            data-plan-clean
          >
            <span
              class="grid size-9 shrink-0 place-items-center rounded-full border border-border bg-card"
              aria-hidden="true"
            >
              <Icon name="lucide:list-checks" class="size-4 text-muted-foreground" />
            </span>
            <div class="min-w-0 flex-1 basis-60">
              <p class="op-body">
                <b class="font-semibold"
                  >+{{ planGroups.clean.length }} produtos sem ressalva</b
                >
                <span class="text-muted-foreground">
                  · insumos ok, sem encomenda, sem falta nem sobra repetida</span
                >
              </p>
              <p class="truncate op-micro text-muted-foreground">
                {{ cleanSummary }}
              </p>
            </div>
            <NuxtButton
              color="neutral"
              variant="outline"
              icon="i-lucide-list"
              label="Ver um a um"
              data-plan-clean-expand
              @click="expandClean = true"
            />
            <NuxtButton
              color="primary"
              variant="outline"
              icon="i-lucide-check-check"
              :disabled="
                !canPlanCleanSet || bulkSubmitting || inlineSubmitting != null
              "
              :aria-busy="bulkSubmitting"
              :label="
                bulkSubmitting
                  ? 'Planejando…'
                  : `Planejar os ${planGroups.clean.length} como sugerido`
              "
              data-plan-clean-all
              @click="planCleanSet()"
            />
          </div>

          <!-- Sem sugestão para o dia (bases, recheios, o que não vende hoje): conjunto
               que se abre para planejar à mão. -->
          <div
            v-if="planGroups.manual.length"
            class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-muted/25 px-4 py-3 last:border-b-0 lg:min-h-16"
            data-plan-manual
          >
            <span
              class="grid size-9 shrink-0 place-items-center rounded-full border border-border bg-card"
              aria-hidden="true"
            >
              <Icon name="lucide:pencil-line" class="size-4 text-muted-foreground" />
            </span>
            <div class="min-w-0 flex-1 basis-60">
              <p class="op-body">
                <b class="font-semibold"
                  >+{{ planGroups.manual.length }} produtos sem sugestão para o dia</b
                >
                <span class="text-muted-foreground">
                  · sem venda que sustente um número; planeje à mão se precisar</span
                >
              </p>
              <p class="truncate op-micro text-muted-foreground">
                {{ manualSummary }}
              </p>
            </div>
            <NuxtButton
              color="neutral"
              variant="outline"
              icon="i-lucide-list"
              label="Ver um a um"
              data-plan-manual-expand
              @click="expandManual = true"
            />
          </div>

          <!-- Planejado vira estado; corrigir e ver encomendas descem para o menu. -->
          <template v-if="planGroups.planned.length">
            <div
              class="flex h-9 items-center gap-2 border-b border-border bg-muted/60 px-4"
            >
              <span class="op-eyebrow text-muted-foreground">Planejados</span>
              <span class="op-micro tnum text-muted-foreground">{{
                planGroups.planned.length
              }}</span>
            </div>
            <!-- Uma linha só, como a prévia v4 (pino 8): o estado, depois cada produto com
                 o número; tocar no produto abre Corrigir, Novo lote e Ver encomendas. -->
            <div
              class="flex flex-wrap items-center gap-x-1 gap-y-1 bg-success/5 px-4 py-2"
              data-planned-line
            >
              <span
                class="mr-2 inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-success/12 px-3 op-label font-semibold text-success"
              >
                <Icon name="lucide:check" class="size-4" />
                Planejado<template v-if="plannedTime">
                  <span class="tnum" data-planned-time>{{ plannedTime }}</span></template
                >
              </span>
              <!-- O "·" anda colado ao fim do item: quando a linha quebra ele fica no fim
                   da linha, nunca sozinho no começo dela; no celular, um item por vez,
                   ele some (R07). -->
              <span
                v-for="(row, index) in planGroups.planned"
                :key="row.output_sku"
                class="inline-flex items-center"
                data-planned-item
              >
                <NuxtDropdownMenu
                  :items="plannedItemMenu(row)"
                  :content="{ align: 'start', sideOffset: 4 }"
                >
                  <NuxtButton
                    color="neutral"
                    variant="ghost"
                    class="px-1.5"
                    :aria-label="`${rowLabel(row)}, ${plannedStateLabel(row).toLowerCase()} ${plannedQtyLabel(row)}: corrigir, novo lote, encomendas`"
                    data-planned-row
                    :data-sku="row.output_sku"
                  >
                    {{ rowLabel(row) }}
                    <b class="tnum whitespace-nowrap">{{
                      formatQty(plannedQtyLabel(row), row.output_unit)
                    }}</b>
                    <Icon
                      v-if="rowCommittedUnits(row) > 0"
                      name="lucide:shopping-bag"
                      class="size-3.5 text-info"
                    />
                  </NuxtButton>
                </NuxtDropdownMenu>
                <span
                  v-if="index < planGroups.planned.length - 1"
                  class="pl-0.5 text-muted-foreground max-sm:hidden"
                  aria-hidden="true"
                  data-planned-separator
                  >·</span
                >
              </span>
              <span
                v-if="allPlannedAsSuggested"
                class="ml-2 op-label text-muted-foreground"
                data-planned-as-suggested
                >como sugerido</span
              >
              <!-- O ⋯ da linha (o único da suíte): corrigir um planejado, um produto por vez. -->
              <OperatorMoreMenu
                label="Mais ações dos planejados"
                class="ml-auto"
                :items="plannedLineMenu"
                data-planned-line-menu
              />
            </div>
          </template>
          <p
            v-if="!visibleRowCount"
            class="p-6 text-center op-body text-muted-foreground"
          >
            Nenhum produto neste recorte.
          </p>
        </div>

        <!-- ── Abertura ─────────────────────────────────────────────────────── -->
        <div
          v-else
          class="overflow-hidden rounded-lg border border-border bg-card"
          data-open-table
        >
          <div
            class="hidden h-10 items-center gap-4 border-b border-border bg-muted/60 px-4 op-eyebrow text-muted-foreground lg:grid"
            :class="openCols"
            aria-hidden="true"
          >
            <span>Produto</span>
            <span>Situação</span>
            <span class="text-right">{{
              lens.read.visible ? (docked ? "Planej." : lens.read.label) : ""
            }}</span>
            <span class="text-right">{{
              lens.action.visible ? lens.action.label : ""
            }}</span>
            <span class="text-right">Ação</span>
          </div>
          <!-- Segurar a linha (toque) ou o clique direito (mouse) abre o MESMO menu do ⋯:
               as ações da linha são uma lista só (`openRowMenu`). -->
          <NuxtContextMenu
            v-for="row in openGroups.rows"
            :key="row.output_sku"
            :items="moreMenuGroups(openRowMenu(row))"
            :data-open-row-context="row.output_sku"
          >
            <div
              class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 border-b border-border px-4 py-2.5 last:border-b-0 lg:h-14 lg:py-0"
              :class="[
                openCols,
                openRowPending(row) ? '' : 'bg-success/5',
                docked && startRow?.output_sku === row.output_sku
                  ? 'shadow-[inset_4px_0_0_var(--primary)] bg-primary/5'
                  : '',
              ]"
              data-open-row
              :data-sku="row.output_sku"
            >
              <div class="min-w-0" data-row-product>
                <p class="truncate op-title">{{ rowLabel(row) }}</p>
                <p class="flex items-center gap-1.5 op-micro text-muted-foreground">
                  <span class="truncate font-mono">{{ row.output_sku }}</span>
                  <!-- Celular e tablet em pé: sem a coluna Planejado, o número vem aqui. -->
                  <span
                    v-if="row.started_qty === '0' && row.planned_qty !== '0' && lens.read.visible"
                    class="shrink-0 tabular-nums lg:hidden"
                    data-open-planned-compact
                    >· {{ formatQty(row.planned_qty, row.output_unit) }} planejadas</span
                  >
                  <NuxtButton
                    v-if="rowCommittedUnits(row) > 0"
                    color="neutral"
                    variant="ghost"
                    icon="i-lucide-shopping-bag"
                    class="shrink-0 tabular-nums"
                    :ui="{ leadingIcon: 'text-info' }"
                    :label="commitmentChipLabel(row)"
                    :aria-label="`${commitmentChipLabel(row)}: unidades de ${rowLabel(row)} comprometidas com encomendas`"
                    data-commitment-chip
                    @click="commitmentsRow = row"
                  />
                </p>
              </div>
              <span class="hidden lg:inline-flex">
                <NuxtBadge
                  :color="openRowPending(row) ? 'warning' : 'success'"
                  :label="openRowPending(row) ? 'A confirmar' : 'Aberto'"
                />
              </span>
              <span
                v-if="lens.read.visible"
                class="hidden text-right text-lg font-semibold tabular-nums lg:block"
                :class="row.planned_qty === '0' ? 'text-muted-foreground' : ''"
                >{{ row.planned_qty === "0" ? "—" : formatQty(row.planned_qty, row.output_unit) }}</span
              >
              <span v-else class="hidden lg:block" />
              <!-- Previsto: o número abre a conferência e o cancelamento do lote aberto. -->
              <span v-if="lens.action.visible" class="hidden justify-end lg:flex">
                <span
                  v-if="row.started_qty !== '0'"
                  class="inline-flex items-center gap-1.5 text-lg font-semibold tabular-nums"
                  >{{ formatQty(row.started_qty, row.output_unit) }}
                  <Icon name="lucide:circle-check" class="size-4 text-success"
                /></span>
                <span
                  v-else
                  class="text-lg font-semibold tabular-nums text-muted-foreground"
                  >{{ cellQty(row.started_qty) }}</span
                >
              </span>
              <span v-else class="hidden lg:block" />
              <div class="flex items-center justify-end gap-1.5">
                <!-- No celular e no tablet em pé o previsto vem junto da ação. -->
                <span
                  v-if="row.started_qty !== '0' && lens.action.visible"
                  class="inline-flex h-8 items-center gap-1.5 px-1 text-base font-semibold tabular-nums lg:hidden"
                  data-open-started-compact
                  >{{ formatQty(row.started_qty, row.output_unit) }}
                  <Icon name="lucide:circle-check" class="size-4 text-success"
                /></span>
                <!-- Confirmando: o painel encaixado está aberto nesta linha (tablet deitado). -->
                <NuxtButton
                  v-if="docked && startRow?.output_sku === row.output_sku"
                  size="xl"
                  trailing-icon="i-lucide-chevron-right"
                  label="Confirmando"
                  data-open-confirming
                  @click="startRow = null"
                />
                <!-- Tablet deitado: os botões da linha crescem para o toque, e só o que
                     está sendo confirmado (acima) fica cheio. -->
                <NuxtButton
                  v-else-if="row.planned_orders.length && actionEnabled(row)"
                  color="primary"
                  :variant="docked ? 'outline' : 'solid'"
                  :size="docked ? 'xl' : 'md'"
                  icon="i-lucide-check"
                  label="Confirmar"
                  :disabled="isBusy(row.output_sku)"
                  :aria-label="`Confirmar ${rowLabel(row)}`"
                  data-open-confirm
                  @click="openStart(row)"
                />
                <!-- Lote aberto: o que foi lançado, a um toque (v3 "não mudaram"). -->
                <NuxtButton
                  v-else-if="row.started_orders.length"
                  color="neutral"
                  variant="outline"
                  :size="docked ? 'xl' : 'md'"
                  class="hidden sm:inline-flex"
                  label="Ver lançamento"
                  :aria-label="`Ver lançamento de ${rowLabel(row)}`"
                  data-open-view-launch
                  @click="openStarted(row)"
                />
                <!-- ⋯ da linha; no tablet deitado o mesmo menu abre ao segurar a linha. -->
                <OperatorMoreMenu
                  :label="`Mais ações de ${rowLabel(row)}`"
                  :items="openRowMenu(row)"
                  :class="docked ? 'lg:hidden' : ''"
                  data-open-row-menu
                />
              </div>
            </div>
          </NuxtContextMenu>
          <p
            v-if="!openGroups.rows.length"
            class="p-6 text-center op-body text-muted-foreground"
          >
            Nenhum produto neste recorte.
          </p>
        </div>
        <p
          v-if="stage === 'open' && docked && openGroups.rows.length"
          class="mt-2.5 flex items-center gap-2 op-micro text-muted-foreground"
          data-open-press-hint
        >
          <Icon name="lucide:pointer" class="size-4" />
          Pressione e segure uma linha: Ver lançamento · Ver encomendas · Cancelar lote.
        </p>
        <p
          v-if="query && !stageRows.length"
          class="mt-3 text-center op-body text-muted-foreground"
        >
          Nenhum resultado para “{{ query.trim() }}”.
        </p>
      </template>
    </section>

    <!-- Painel de confirmação encaixado (tablet deitado): lote em blocos, quantidade
         com − / + no tamanho do toque, numérico na tela e "Confirmar N un." no polegar. -->
    <aside
      v-if="docked && startRow"
      class="flex w-[392px] shrink-0 flex-col border-l border-border bg-card"
      aria-label="Confirmar o previsto"
      data-open-confirm-panel
    >
      <header class="flex items-start gap-3 border-b border-border px-5 pt-4 pb-3.5">
        <div class="min-w-0 flex-1">
          <p class="op-eyebrow text-muted-foreground">Quanto está previsto?</p>
          <h2 class="truncate op-heading leading-tight">
            {{ rowLabel(startRow) }}
          </h2>
          <p class="op-micro text-muted-foreground">
            {{ startRow.output_sku }} · esta quantidade segue para o Fechamento.
          </p>
        </div>
        <NuxtButton
          icon="i-lucide-x"
          color="neutral"
          variant="ghost"
          size="xl"
          square
          aria-label="Fechar"
          @click="
            startRow = null;
            selectedStartPk = null;
          "
        />
      </header>
      <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
        <template v-if="startRow.planned_orders.length > 1">
          <p class="op-label text-muted-foreground">Lote que vai confirmar</p>
          <div class="grid grid-cols-2 gap-2">
            <NuxtButton
              v-for="workOrder in startRow.planned_orders"
              :key="workOrder.pk"
              color="neutral"
              variant="outline"
              size="xl"
              block
              :active="selectedStartPk === workOrder.pk"
              active-color="primary"
              active-variant="outline"
              :ui="{ base: 'h-auto flex-col items-start justify-start text-left' }"
              :aria-pressed="selectedStartPk === workOrder.pk"
              @click="selectStartWorkOrder(workOrder)"
            >
              <span class="op-title">#{{ workOrder.ref }}</span>
              <span class="op-micro text-muted-foreground"
                >planejado {{ workOrder.planned_qty }} un.</span
              >
            </NuxtButton>
          </div>
        </template>
        <p v-else-if="selectedStartOrder" class="op-label text-muted-foreground">
          Lote #{{ selectedStartOrder.ref }} · planejado {{ selectedStartOrder.planned_qty }} un.
        </p>
        <template v-if="selectedStartOrder">
          <div class="flex items-center gap-2">
            <NuxtButton
              icon="i-lucide-minus"
              color="neutral"
              variant="outline"
              size="xl"
              square
              aria-label="Diminuir"
              @click="bump('start', -1)"
            />
            <NuxtInput
              ref="startQtyInput"
              v-model="startQty"
              inputmode="none"
              size="xl"
              color="primary"
              highlight
              class="w-full"
              :ui="{ base: 'text-center text-3xl font-bold tabular-nums' }"
              aria-label="Quantidade prevista"
              @keydown.enter.prevent="confirmStart()"
            />
            <NuxtButton
              icon="i-lucide-plus"
              color="neutral"
              variant="outline"
              size="xl"
              square
              aria-label="Aumentar"
              @click="bump('start', 1)"
            />
          </div>
          <p v-if="startDiverges" class="op-label text-muted-foreground">
            Diferente do planejado ({{ selectedStartOrder.planned_qty }}). É rendimento, não perda.
          </p>
          <OperatorNumpad
            class="[&_button]:h-14! [&_button]:op-figure"
            subject="quantidade prevista"
            @digit="startDigit"
            @backspace="startBackspace"
            @clear="startClear"
          />
        </template>
      </div>
      <footer class="flex gap-2 border-t border-border px-5 py-4">
        <NuxtButton
          color="neutral"
          variant="outline"
          size="xl"
          block
          class="flex-1"
          label="Cancelar"
          @click="
            startRow = null;
            selectedStartPk = null;
          "
        />
        <NuxtButton
          size="xl"
          block
          class="flex-[1.6]"
          icon="i-lucide-check"
          :disabled="startSubmitting || !startReady"
          :label="
            startSubmitting
              ? 'Confirmando…'
              : `Confirmar ${formatQtyUnit(startQty || '0', startRow.output_unit)}`
          "
          data-open-confirm-submit
          @click="confirmStart()"
        />
      </footer>
    </aside>
    </div>

    <!-- planejar -->
    <NuxtModal
      :open="planRow != null"
      :title="`${PLAN_TITLE[planMode]} · ${planRow ? rowLabel(planRow) : ''}`"
      :description="planDescription"
      :ui="{ content: 'sm:max-w-sm' }"
      @update:open="
        (v: boolean) => {
          if (!v) {
            planRow = null;
            selectedPlannedPk = null;
          }
        }
      "
    >
      <template #body>
        <div class="flex flex-col gap-3">
          <div
            v-if="
              planRow &&
              planRow.planned_orders.length > 1 &&
              !selectedPlannedOrder
            "
            class="grid gap-2"
          >
            <p class="text-sm text-muted-foreground">
              Selecione o lote exato que deseja ajustar.
            </p>
            <!-- O bloco do lote carrega referência e quantidade; é seleção de registro. -->
            <NuxtButton
              v-for="workOrder in planRow.planned_orders"
              :key="workOrder.pk"
              color="neutral"
              variant="outline"
              size="xl"
              block
              :ui="{ base: 'justify-between' }"
              @click="selectPlannedWorkOrder(workOrder)"
            >
              <span class="font-medium">#{{ workOrder.ref }}</span>
              <span class="tabular-nums text-muted-foreground"
                >{{ workOrder.planned_qty }} un.</span
              >
            </NuxtButton>
          </div>
          <p
            v-if="planMode === 'adjust' && selectedPlannedOrder"
            class="text-sm text-muted-foreground"
          >
            Substitui #{{ selectedPlannedOrder.ref }} ({{
              selectedPlannedOrder.planned_qty
            }}). Zero remove.
          </p>
          <p
            v-else-if="planMode === 'new-batch'"
            class="text-sm text-muted-foreground"
          >
            Soma ao dia<template v-if="planRow?.started_qty !== '0'">
              · {{ planRow?.started_qty }} previstas</template
            ><template v-if="planRow?.finished_qty !== '0'">
              · {{ planRow?.finished_qty }} realizadas</template
            >.
          </p>
          <div
            v-if="!planRow?.planned_orders.length || selectedPlannedOrder"
            class="flex items-center gap-2"
          >
            <NuxtButton
              icon="i-lucide-minus"
              color="neutral"
              variant="outline"
              size="xl"
              square
              :disabled="planSource === 'suggested'"
              aria-label="Diminuir"
              @click="bump('plan', -1)"
            />
            <NuxtInput
              ref="planQtyInput"
              v-model="planQty"
              inputmode="decimal"
              size="xl"
              class="w-full"
              :ui="{ base: 'text-center text-3xl font-bold tabular-nums' }"
              :readonly="planSource === 'suggested'"
              aria-label="Quantidade planejada"
              @keydown.enter.prevent="confirmPlan()"
            />
            <NuxtButton
              icon="i-lucide-plus"
              color="neutral"
              variant="outline"
              size="xl"
              square
              :disabled="planSource === 'suggested'"
              aria-label="Aumentar"
              @click="bump('plan', 1)"
            />
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton
            color="neutral"
            variant="outline"
            size="xl"
            label="Cancelar"
            @click="planRow = null"
          />
          <NuxtButton
            size="xl"
            :disabled="
              !planQty.trim() ||
              !planQtyValid ||
              !planActionAllowed ||
              planSubmitting ||
              (!!planRow?.planned_orders.length && !selectedPlannedOrder)
            "
            aria-keyshortcuts="Enter"
            :label="
              planSubmitting
                ? 'Confirmando…'
                : planMode === 'new-batch'
                  ? 'Confirmar novo lote'
                  : 'Confirmar'
            "
            @click="confirmPlan()"
          />
        </div>
      </template>
    </NuxtModal>

    <!-- Confirmar: o previsto abre o lote e segue para o Fechamento (evento interno: start) -->
    <NuxtModal
      :open="startRow != null && !docked"
      :title="`Quanto está previsto? · ${startRow ? rowLabel(startRow) : ''}`"
      :description="`${startRow?.output_sku ?? ''} · esta quantidade abre o lote e segue para o Fechamento.`"
      :ui="{ content: 'sm:max-w-sm' }"
      @update:open="
        (v: boolean) => {
          if (!v) {
            startRow = null;
            selectedStartPk = null;
          }
        }
      "
    >
      <template #body>
        <div class="flex flex-col gap-3">
          <div
            v-if="
              startRow &&
              startRow.planned_orders.length > 1 &&
              !selectedStartOrder
            "
            class="grid gap-2"
          >
            <p class="text-sm text-muted-foreground">
              Selecione o lote que vai confirmar.
            </p>
            <!-- O bloco do lote carrega referência e quantidade; é seleção de registro. -->
            <NuxtButton
              v-for="workOrder in startRow.planned_orders"
              :key="workOrder.pk"
              color="neutral"
              variant="outline"
              size="xl"
              block
              :ui="{ base: 'justify-between' }"
              @click="selectStartWorkOrder(workOrder)"
            >
              <span class="font-medium">#{{ workOrder.ref }}</span>
              <span class="tabular-nums text-muted-foreground"
                >{{ workOrder.planned_qty }} un.</span
              >
            </NuxtButton>
          </div>
          <p v-if="selectedStartOrder" class="text-sm text-muted-foreground">
            Lote #{{ selectedStartOrder.ref }} · planejado
            {{ selectedStartOrder.planned_qty }}
          </p>
          <div v-if="selectedStartOrder" class="flex items-center gap-2">
            <NuxtButton
              icon="i-lucide-minus"
              color="neutral"
              variant="outline"
              size="xl"
              square
              aria-label="Diminuir"
              @click="bump('start', -1)"
            />
            <NuxtInput
              ref="startQtyInput"
              v-model="startQty"
              inputmode="decimal"
              size="xl"
              class="w-full"
              :ui="{ base: 'text-center text-3xl font-bold tabular-nums' }"
              aria-label="Quantidade prevista"
              @keydown.enter.prevent="confirmStart()"
            />
            <NuxtButton
              icon="i-lucide-plus"
              color="neutral"
              variant="outline"
              size="xl"
              square
              aria-label="Aumentar"
              @click="bump('start', 1)"
            />
          </div>
          <!-- Divergiu do planejado? A tela avisa e segue: é rendimento, não perda. -->
          <p
            v-if="selectedStartOrder && startDiverges"
            class="text-sm text-muted-foreground"
          >
            Diferente do planejado ({{ selectedStartOrder.planned_qty }}).
          </p>
        </div>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton
            color="neutral"
            variant="outline"
            size="xl"
            label="Cancelar"
            @click="startRow = null"
          />
          <NuxtButton
            size="xl"
            :disabled="startSubmitting || !startReady"
            aria-keyshortcuts="Enter"
            :label="startSubmitting ? 'Confirmando…' : 'Confirmar'"
            @click="confirmStart()"
          />
        </div>
      </template>
    </NuxtModal>

    <!-- lote aberto: conferência e cancelamento, sem etapas, sem gestão -->
    <NuxtModal
      :open="startedRow != null"
      :title="`${startedRow?.started_orders.length ? 'Lote aberto' : 'Lote planejado'} · ${startedRow ? rowLabel(startedRow) : ''}`"
      :description="startedDescription"
      @update:open="
        (v: boolean) => {
          if (!v) {
            startedRow = null;
            selectedStartedPk = null;
            voidConfirming = false;
          }
        }
      "
    >
      <template #body>
        <div class="flex flex-col gap-3">
          <div
            v-if="
              startedRow &&
              startedDialogOrders.length > 1 &&
              !selectedStartedOrder
            "
            class="grid gap-2"
          >
            <!-- O bloco do lote carrega referência e quantidade; é seleção de registro. -->
            <NuxtButton
              v-for="workOrder in startedDialogOrders"
              :key="workOrder.pk"
              color="neutral"
              variant="outline"
              size="xl"
              block
              :ui="{ base: 'justify-between' }"
              @click="selectedStartedPk = workOrder.pk"
            >
              <span class="font-medium">#{{ workOrder.ref }}</span>
              <span class="tabular-nums text-muted-foreground"
                >{{ workOrder.started_qty || workOrder.planned_qty }} un.</span
              >
            </NuxtButton>
          </div>

          <template v-if="voidConfirming">
            <NuxtAlert
              color="warning"
              variant="subtle"
              icon="i-lucide-triangle-alert"
              :description="
                startedRow?.started_orders.length
                  ? 'O lote volta atrás e o vínculo com pedidos é desfeito.'
                  : 'O lote planejado sai do dia e o vínculo com pedidos é desfeito.'
              "
            />
            <NuxtTextarea
              v-model="voidReason"
              :rows="2"
              class="w-full"
              placeholder="Motivo do cancelamento…"
              aria-label="Motivo do cancelamento"
            />
          </template>
        </div>
      </template>
      <template #footer>
        <div class="flex w-full flex-wrap gap-2">
          <NuxtButton
            v-if="selectedStartedOrder && !voidConfirming"
            color="error"
            variant="outline"
            label="Cancelar lote…"
            @click="voidConfirming = true"
          />
          <NuxtButton
            v-else-if="selectedStartedOrder"
            color="error"
            label="Confirmar cancelamento"
            @click="confirmVoid()"
          />
          <NuxtButton
            color="neutral"
            variant="outline"
            class="ml-auto"
            label="Voltar"
            @click="
              startedRow = null;
              selectedStartedPk = null;
              voidConfirming = false;
            "
          />
        </div>
      </template>
    </NuxtModal>

    <!-- pedidos vinculados -->
    <NuxtModal
      :open="commitmentsRow != null"
      :title="`${commitmentsRow ? rowCommittedUnits(commitmentsRow) : 0} un. comprometidas · ${commitmentsRow ? rowLabel(commitmentsRow) : ''}`"
      :description="`${commitmentsRow?.output_sku ?? ''} · encomendas confirmadas que dependem desta produção.`"
      @update:open="
        (v: boolean) => {
          if (!v) commitmentsRow = null;
        }
      "
    >
      <template #body>
        <ul class="flex flex-col gap-2 text-sm">
          <li
            v-for="commitment in commitmentsList"
            :key="commitment.ref"
            class="flex items-center justify-between gap-3 rounded-md border p-2.5"
          >
            <span class="inline-flex items-center gap-2">
              <Icon
                name="lucide:shopping-bag"
                class="size-4 text-muted-foreground"
              />
              <span class="font-medium">{{ commitment.ref }}</span>
              <NuxtBadge color="neutral" :label="commitment.status_label" />
            </span>
            <span class="tabular-nums text-muted-foreground"
              >{{ commitment.qty_required }} un.</span
            >
          </li>
        </ul>
      </template>
      <template #footer>
        <div class="flex w-full justify-end">
          <NuxtButton
            color="neutral"
            variant="outline"
            label="Fechar"
            @click="commitmentsRow = null"
          />
        </div>
      </template>
    </NuxtModal>

    <ShortageDialog
      :shortage="shortage"
      @update:open="
        (v: boolean) => {
          if (!v) closeShortage();
        }
      "
      @confirm="retryPlanWithForce"
      @review="reviewShortage"
    />
  </main>
</template>
