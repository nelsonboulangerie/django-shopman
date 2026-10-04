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
import { nextTick } from "vue";

import {
  boardDisplay,
  fullDateLabel,
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

const emptyCopy = computed(() =>
  props.stage === "plan"
    ? { text: "Nenhuma receita ativa.", cta: "", to: "" }
    : {
        text: "Nada planejado para produzir nesta data.",
        cta: "Ir para o Planejamento",
        to: "/plan",
      },
);

// ── Overlays ────────────────────────────────────────────────────────────────
// O "Por quê" abre ancorado na linha (um por vez); a linha fica marcada
// enquanto ele está aberto.
const reasonSku = ref<string | null>(null);
const reasonTriggers = new Map<string, HTMLElement>();
const planRow = ref<ProductionMatrixRowProjection | null>(null);
const planQty = ref("");
const planQtyInput = ref<HTMLInputElement | null>(null);
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
const startQtyInput = ref<HTMLInputElement | null>(null);
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

const selectedStartedOrder = computed<WorkOrderCardProjection | null>(
  () =>
    startedRow.value?.started_orders.find(
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
    void nextTick(() => planQtyInput.value?.focus());
  }
}

function selectPlannedWorkOrder(workOrder: WorkOrderCardProjection) {
  selectedPlannedPk.value = workOrder.pk;
  if (planSource.value === "manual") planQty.value = workOrder.planned_qty;
  void nextTick(() => planQtyInput.value?.focus());
}

function toggleReason(row: ProductionMatrixRowProjection) {
  reasonSku.value = reasonSku.value === row.output_sku ? null : row.output_sku;
}

function closeReason(outputSku: string) {
  if (reasonSku.value === outputSku) reasonSku.value = null;
}

function rememberReasonTrigger(outputSku: string, el: unknown) {
  if (el instanceof HTMLElement) reasonTriggers.set(outputSku, el);
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
    void nextTick(() => startQtyInput.value?.focus());
  }
}

function selectStartWorkOrder(workOrder: WorkOrderCardProjection) {
  selectedStartPk.value = workOrder.pk;
  startQty.value = workOrder.planned_qty;
  void nextTick(() => startQtyInput.value?.focus());
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
    void nextTick(() => startQtyInput.value?.focus());
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
  void nextTick(() => planQtyInput.value?.focus());
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

const PLAN_FILTERS: Array<{ key: PlanFilter; label: string; dot: string }> = [
  { key: "all", label: "Todos", dot: "" },
  { key: "todo", label: "A planejar", dot: "bg-primary" },
  { key: "flagged", label: "Com ressalva", dot: "bg-warning" },
  { key: "done", label: "Planejados", dot: "bg-success" },
];
const OPEN_FILTERS: Array<{ key: OpenFilter; label: string; dot: string }> = [
  { key: "all", label: "Todos", dot: "" },
  { key: "pending", label: "A confirmar", dot: "bg-warning" },
  { key: "opened", label: "Abertos", dot: "bg-success" },
];

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
function plannedStateLabel(row: ProductionMatrixRowProjection): string {
  if (row.planned_qty !== "0") return "Planejado";
  return row.started_qty !== "0" ? "Aberto" : "Fechado";
}

const signalClass = {
  danger: "bg-destructive/10 text-destructive",
  warning: "bg-warning/15 text-warning",
} as const;

const plannedMenuSku = ref<string | null>(null);
function plannedMenu(row: ProductionMatrixRowProjection, open: boolean) {
  plannedMenuSku.value = open ? row.output_sku : null;
}
function fromPlannedMenu(action: () => void) {
  plannedMenuSku.value = null;
  action();
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <!-- Cabeçalho de UMA linha (prévia v4 `plano-porque4.html`): título, ao vivo, busca,
         "4 de 28 planejados" com a barra, o dia e o ⋯. Os recortes na segunda linha. -->
    <ProductionHeader
      v-model:query="query"
      :title="title"
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
      <template #actions>
        <OperatorPeriodPicker
          v-model="period"
          :presets="['day']"
          :today="todayISO"
          label="Data"
          align="end"
        />
      </template>
      <template #filters>
        <template v-if="stage === 'plan'">
          <UiFilterChip
            v-for="filter in PLAN_FILTERS"
            :key="filter.key"
            :active="planFilter === filter.key"
            :count="planGroups.counts[filter.key]"
            :aria-pressed="planFilter === filter.key"
            :data-plan-filter="filter.key"
            @click="planFilter = filter.key"
          >
            <template #icon>
              <Icon
                v-if="planFilter === filter.key && !filter.dot"
                name="lucide:check"
                class="size-4 text-primary"
              />
              <span
                v-else-if="filter.dot"
                class="size-2 rounded-full"
                :class="filter.dot"
                aria-hidden="true"
              />
            </template>
            {{ filter.label }}
          </UiFilterChip>
        </template>
        <template v-else>
          <UiFilterChip
            v-for="filter in OPEN_FILTERS"
            :key="filter.key"
            :active="openFilter === filter.key"
            :count="openGroups.counts[filter.key]"
            :aria-pressed="openFilter === filter.key"
            :data-open-filter="filter.key"
            @click="openFilter = filter.key"
          >
            <template #icon>
              <Icon
                v-if="openFilter === filter.key && !filter.dot"
                name="lucide:check"
                class="size-4 text-primary"
              />
              <span
                v-else-if="filter.dot"
                class="size-2 rounded-full"
                :class="filter.dot"
                aria-hidden="true"
              />
            </template>
            {{ filter.label }}
          </UiFilterChip>
        </template>
        <template v-if="baseOptions.length">
          <span class="mx-1 h-6 w-px bg-border" aria-hidden="true" />
          <label
            class="relative inline-flex min-h-control items-center gap-2 rounded-full border border-border bg-card px-3 op-label transition hover:bg-accent"
            :class="baseFilter ? 'border-primary bg-primary/10 font-semibold' : ''"
          >
            <Icon name="lucide:layers" class="size-4" aria-hidden="true" />
            <span aria-hidden="true">Base: {{ baseLabel }}</span>
            <Icon name="lucide:chevron-down" class="size-4 text-muted-foreground" aria-hidden="true" />
            <select
              v-model="baseFilter"
              class="absolute inset-0 cursor-pointer opacity-0"
              aria-label="Filtrar por ficha-base"
            >
              <option value="">Todas as bases</option>
              <option
                v-for="base in baseOptions"
                :key="base.output_sku"
                :value="base.output_sku"
              >
                {{ base.name }} ({{ base.count }})
              </option>
            </select>
          </label>
        </template>
      </template>
    </ProductionHeader>

    <section class="min-h-0 flex-1 overflow-auto px-3 pt-3 pb-4 md:px-4">
      <p v-if="display === 'loading'" class="op-body text-muted-foreground">
        Carregando…
      </p>

      <!-- Erro só toma a tela quando NÃO há dado nenhum a mostrar (acolhedor, não tela branca). -->
      <div
        v-else-if="display === 'error'"
        class="grid place-items-center gap-2 rounded-lg border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
        <p class="op-title text-foreground">
          Não foi possível carregar o quadro.
        </p>
        <p class="op-body">Estamos tentando reconectar sozinhos.</p>
        <UiButton
          type="button"
          class="mt-1 min-h-11"
          variant="outline"
          size="sm"
          @click="refresh()"
        >
          <Icon name="lucide:refresh-cw" class="size-4" /> Tentar de novo
        </UiButton>
      </div>

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

        <div
          v-if="!stageRows.length"
          class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground"
        >
          <Icon name="lucide:layout-grid" class="size-8" />
          <p class="op-title">{{ emptyCopy.text }}</p>
          <NuxtLink
            v-if="emptyCopy.to"
            :to="emptyCopy.to"
            class="inline-flex min-h-11 items-center op-label font-semibold text-primary underline-offset-2 hover:underline"
          >
            {{ emptyCopy.cta }}
          </NuxtLink>
        </div>

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
              <button
                v-if="rowCommittedUnits(row) > 0"
                type="button"
                class="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full bg-info/12 px-2 text-xs font-semibold tabular-nums text-info transition hover:bg-info/20"
                :aria-label="`${rowCommittedUnits(row)} unidades de ${rowLabel(row)} comprometidas com pedidos`"
                @click="commitmentsRow = row"
              >
                <Icon name="lucide:shopping-bag" class="size-3.5" />
                {{ rowCommittedUnits(row) }} un.
              </button>
            </div>

            <!-- Sugestão: o número e, no máximo, um sinal. A conta mora no "Por quê",
                 que abre ancorado na linha (UX-P2, L3). -->
            <div
              class="flex min-w-0 flex-1 items-center gap-2.5 max-sm:w-full max-sm:flex-none lg:flex-none"
            >
              <template v-if="lens.read.visible">
                <UiPopover
                  v-if="row.suggestion"
                  :open="reasonSku === row.output_sku"
                  @update:open="
                    (open: boolean) => {
                      if (!open) closeReason(row.output_sku);
                    }
                  "
                >
                  <UiPopoverAnchor as-child>
                    <span class="flex min-w-0 flex-1 items-center gap-2.5">
                      <span
                        class="min-w-[30px] op-heading tnum"
                        :class="
                          draftChanged(row) || row.suggestion.quantity === '0'
                            ? 'text-muted-foreground'
                            : ''
                        "
                        >{{ row.suggestion.quantity }}</span
                      >
                      <span
                        v-if="draftChanged(row)"
                        class="op-label leading-tight text-muted-foreground"
                        data-plan-changed
                      >
                        você mudou de {{ row.suggestion.quantity }}<br />
                        <button
                          type="button"
                          class="font-semibold text-primary underline underline-offset-2"
                          @click="resetDraft(row)"
                        >
                          voltar
                        </button>
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
                      <button
                        :ref="(el) => rememberReasonTrigger(row.output_sku, el)"
                        type="button"
                        data-plan-reason-trigger
                        class="ml-auto inline-flex min-h-11 shrink-0 items-center gap-[5px] rounded-md px-2 op-label font-semibold text-muted-foreground transition hover:bg-accent hover:text-foreground"
                        :class="
                          reasonSku === row.output_sku
                            ? 'bg-primary/12 text-primary shadow-[inset_0_0_0_1.5px_var(--primary)]'
                            : ''
                        "
                        aria-haspopup="dialog"
                        :aria-expanded="reasonSku === row.output_sku"
                        :aria-label="`Por que ${row.suggestion.quantity} de ${rowLabel(row)}?`"
                        @click="toggleReason(row)"
                      >
                        <Icon name="lucide:info" class="size-4" />
                        Por quê
                      </button>
                    </span>
                  </UiPopoverAnchor>
                  <UiPopoverContent
                    side="bottom"
                    align="end"
                    :side-offset="6"
                    :collision-padding="16"
                    class="w-[33rem] max-w-[calc(100vw-2rem)] rounded-xl p-0 shadow-[0_18px_48px_-8px_rgb(40_25_10/.35),0_4px_12px_rgb(40_25_10/.15)]"
                    :aria-label="`Por que ${row.suggestion.quantity} de ${rowLabel(row)}`"
                    @interact-outside="onReasonOutside"
                    @close-auto-focus="
                      (event: Event) => returnReasonFocus(event, row.output_sku)
                    "
                  >
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
                  </UiPopoverContent>
                </UiPopover>
                <span
                  v-else
                  class="op-heading text-muted-foreground"
                  title="Sem sugestão para este produto"
                  >—</span
                >
              </template>
            </div>

            <!-- Quantidade: o stepper na linha; mudou, a sugestão diz "você mudou". -->
            <template v-if="lens.action.visible">
              <div
                class="flex h-[42px] w-[150px] items-center overflow-hidden rounded-md border bg-background max-sm:min-w-[8.5rem] max-sm:flex-1 lg:w-auto"
                :class="
                  draftChanged(row) ? 'border-2 border-primary' : 'border-input'
                "
              >
                <button
                  type="button"
                  class="grid h-full w-[42px] shrink-0 place-items-center border-r border-input transition hover:bg-accent disabled:opacity-40"
                  :disabled="!stepperEditable || !actionEnabled(row)"
                  :aria-label="`Diminuir ${rowLabel(row)}`"
                  @click="bumpDraft(row, -1)"
                >
                  <Icon name="lucide:minus" class="size-4" />
                </button>
                <input
                  :value="draftOf(row)"
                  type="text"
                  inputmode="decimal"
                  class="h-full w-full min-w-0 border-0 bg-transparent text-center op-heading tnum outline-none focus-visible:ring-0"
                  :readonly="!stepperEditable || !actionEnabled(row)"
                  :aria-label="`Quantidade de ${rowLabel(row)}`"
                  @input="
                    setDraft(row, ($event.target as HTMLInputElement).value)
                  "
                  @keydown.enter.prevent="planInline(row)"
                />
                <button
                  type="button"
                  class="grid h-full w-[42px] shrink-0 place-items-center border-l border-input transition hover:bg-accent disabled:opacity-40"
                  :disabled="!stepperEditable || !actionEnabled(row)"
                  :aria-label="`Aumentar ${rowLabel(row)}`"
                  @click="bumpDraft(row, 1)"
                >
                  <Icon name="lucide:plus" class="size-4" />
                </button>
              </div>
              <button
                type="button"
                class="inline-flex h-[42px] items-center justify-center gap-2 whitespace-nowrap rounded-md bg-primary px-4 op-label font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50 max-sm:min-w-[8.5rem] max-sm:flex-1"
                :disabled="
                  !inlineAllowed(row) ||
                  isBusy(row.output_sku) ||
                  inlineSubmitting != null ||
                  bulkSubmitting
                "
                :aria-busy="inlineSubmitting === row.output_sku"
                data-plan-inline
                @click="planInline(row)"
              >
                <Icon name="lucide:check" class="size-4" />
                {{
                  inlineSubmitting === row.output_sku
                    ? "Planejando…"
                    : `Planejar ${draftOf(row)}`
                }}
              </button>
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
            <button
              type="button"
              class="inline-flex h-11 items-center gap-2 rounded-md border border-border bg-card px-4 op-label font-semibold transition hover:bg-accent"
              data-plan-clean-expand
              @click="expandClean = true"
            >
              <Icon name="lucide:list" class="size-4" />
              Ver um a um
            </button>
            <button
              type="button"
              class="inline-flex h-11 items-center gap-2 rounded-md border border-primary px-4 op-label font-semibold text-primary transition hover:bg-primary/10 disabled:opacity-50"
              :disabled="
                !canPlanCleanSet || bulkSubmitting || inlineSubmitting != null
              "
              :aria-busy="bulkSubmitting"
              data-plan-clean-all
              @click="planCleanSet()"
            >
              <Icon name="lucide:check-check" class="size-4" />
              {{
                bulkSubmitting
                  ? "Planejando…"
                  : `Planejar os ${planGroups.clean.length} como sugerido`
              }}
            </button>
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
            <button
              type="button"
              class="inline-flex h-11 items-center gap-2 rounded-md border border-border bg-card px-4 op-label font-semibold transition hover:bg-accent"
              data-plan-manual-expand
              @click="expandManual = true"
            >
              <Icon name="lucide:list" class="size-4" />
              Ver um a um
            </button>
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
                {{ planGroups.planned.length === 1 ? "Planejado" : "Planejados" }}
              </span>
              <template v-for="(row, index) in planGroups.planned" :key="row.output_sku">
                <span
                  v-if="index > 0"
                  class="text-muted-foreground"
                  aria-hidden="true"
                  >·</span
                >
                <UiPopover
                  :open="plannedMenuSku === row.output_sku"
                  @update:open="(open: boolean) => plannedMenu(row, open)"
                >
                  <UiPopoverTrigger as-child>
                    <button
                      type="button"
                      class="inline-flex min-h-11 items-center gap-1.5 rounded-md px-1.5 op-label transition hover:bg-accent"
                      :aria-label="`${rowLabel(row)}, ${plannedStateLabel(row).toLowerCase()} ${plannedQtyLabel(row)}: corrigir, novo lote, encomendas`"
                      data-planned-row
                      :data-sku="row.output_sku"
                    >
                      {{ rowLabel(row) }}
                      <b class="tnum">{{ plannedQtyLabel(row) }}</b>
                      <span
                        v-if="plannedStateLabel(row) !== 'Planejado'"
                        class="op-micro text-muted-foreground"
                        >({{ plannedStateLabel(row).toLowerCase() }})</span
                      >
                      <Icon
                        v-if="rowCommittedUnits(row) > 0"
                        name="lucide:shopping-bag"
                        class="size-3.5 text-info"
                      />
                    </button>
                  </UiPopoverTrigger>
                  <UiPopoverContent
                    align="start"
                    :side-offset="4"
                    class="w-64 p-1.5"
                  >
                    <p class="px-2.5 pt-1.5 op-eyebrow text-muted-foreground">
                      {{ rowLabel(row) }}
                    </p>
                    <p class="px-2.5 pb-1.5 op-micro text-muted-foreground">
                      {{ plannedStateLabel(row) }} {{ plannedQtyLabel(row)
                      }}<template v-if="plannedNote(row)">
                        · {{ plannedNote(row) }}</template
                      >
                    </p>
                    <button
                      type="button"
                      class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent disabled:opacity-50"
                      :disabled="!actionEnabled(row) || isBusy(row.output_sku)"
                      data-planned-correct
                      @click="fromPlannedMenu(() => onAction(row))"
                    >
                      <Icon
                        :name="
                          rowPlanMode(row) === 'new-batch'
                            ? 'lucide:plus'
                            : 'lucide:pencil'
                        "
                        class="size-4 text-muted-foreground"
                      />
                      {{
                        rowPlanMode(row) === "new-batch"
                          ? "Planejar novo lote"
                          : "Corrigir quantidade"
                      }}
                    </button>
                    <button
                      v-if="rowCommittedUnits(row) > 0"
                      type="button"
                      class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent"
                      @click="fromPlannedMenu(() => (commitmentsRow = row))"
                    >
                      <Icon
                        name="lucide:shopping-bag"
                        class="size-4 text-muted-foreground"
                      />
                      Ver encomendas ({{ rowCommittedUnits(row) }} un.)
                    </button>
                  </UiPopoverContent>
                </UiPopover>
              </template>
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
            class="hidden h-10 items-center gap-4 border-b border-border bg-muted/60 px-4 op-eyebrow text-muted-foreground lg:grid lg:grid-cols-[minmax(0,1fr)_150px_110px_110px_170px]"
            aria-hidden="true"
          >
            <span>Produto</span>
            <span>Situação</span>
            <span class="text-right">{{
              lens.read.visible ? lens.read.label : ""
            }}</span>
            <span class="text-right">{{
              lens.action.visible ? lens.action.label : ""
            }}</span>
            <span class="text-right">Ação</span>
          </div>
          <div
            v-for="row in openGroups.rows"
            :key="row.output_sku"
            class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 border-b border-border px-4 py-2.5 last:border-b-0 lg:h-14 lg:grid-cols-[minmax(0,1fr)_150px_110px_110px_170px] lg:py-0"
            :class="openRowPending(row) ? '' : 'bg-success/5'"
            data-open-row
            :data-sku="row.output_sku"
          >
            <div class="min-w-0" data-row-product>
              <p class="truncate op-title">{{ rowLabel(row) }}</p>
              <p class="flex items-center gap-1.5 op-micro text-muted-foreground">
                <span class="truncate font-mono">{{ row.output_sku }}</span>
                <button
                  v-if="rowCommittedUnits(row) > 0"
                  type="button"
                  class="inline-flex h-6 shrink-0 items-center gap-1 rounded-full bg-info/12 px-2 text-xs font-semibold tabular-nums text-info transition hover:bg-info/20"
                  :aria-label="`${rowCommittedUnits(row)} unidades de ${rowLabel(row)} comprometidas com pedidos`"
                  @click="commitmentsRow = row"
                >
                  <Icon name="lucide:shopping-bag" class="size-3" />
                  {{ rowCommittedUnits(row) }} un. encomendadas
                </button>
              </p>
            </div>
            <span
              class="hidden w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold lg:inline-flex"
              :class="
                openRowPending(row)
                  ? 'bg-warning/15 text-warning'
                  : 'bg-success/12 text-success'
              "
            >
              <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
              {{ openRowPending(row) ? "A confirmar" : "Aberto" }}
            </span>
            <span
              v-if="lens.read.visible"
              class="hidden text-right text-lg font-semibold tabular-nums lg:block"
              :class="row.planned_qty === '0' ? 'text-muted-foreground' : ''"
              >{{ cellQty(row.planned_qty) }}</span
            >
            <span v-else class="hidden lg:block" />
            <!-- Previsto: o número abre a conferência e o cancelamento do lote aberto. -->
            <span v-if="lens.action.visible" class="hidden justify-end lg:flex">
              <button
                v-if="row.started_qty !== '0' && actionEnabled(row)"
                type="button"
                class="inline-flex h-10 items-center gap-1.5 rounded-md px-2 text-lg font-semibold tabular-nums transition hover:bg-accent disabled:opacity-50"
                :disabled="isBusy(row.output_sku)"
                :aria-label="`Previsto ${row.started_qty} de ${rowLabel(row)}`"
                @click="openStarted(row)"
              >
                {{ row.started_qty }}
                <Icon name="lucide:circle-check" class="size-4 text-success" />
              </button>
              <span
                v-else
                class="text-lg font-semibold tabular-nums"
                :class="row.started_qty === '0' ? 'text-muted-foreground' : ''"
                >{{ cellQty(row.started_qty) }}</span
              >
            </span>
            <span v-else class="hidden lg:block" />
            <div class="flex items-center justify-end gap-2">
              <!-- No celular e no tablet em pé o previsto vem junto da ação. -->
              <button
                v-if="
                  row.started_qty !== '0' &&
                  actionEnabled(row) &&
                  lens.action.visible
                "
                type="button"
                class="inline-flex h-11 items-center gap-1.5 rounded-md border border-border px-3 text-base font-semibold tabular-nums transition hover:bg-accent lg:hidden"
                :disabled="isBusy(row.output_sku)"
                :aria-label="`Previsto ${row.started_qty} de ${rowLabel(row)}`"
                data-open-started-compact
                @click="openStarted(row)"
              >
                {{ row.started_qty }}
                <Icon name="lucide:circle-check" class="size-4 text-success" />
              </button>
              <button
                v-if="row.planned_orders.length && actionEnabled(row)"
                type="button"
                class="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-primary px-4 op-label font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
                :disabled="isBusy(row.output_sku)"
                :aria-label="`Confirmar ${rowLabel(row)}`"
                @click="openStart(row)"
              >
                <Icon name="lucide:check" class="size-4" />
                Confirmar
              </button>
            </div>
          </div>
          <p
            v-if="!openGroups.rows.length"
            class="p-6 text-center op-body text-muted-foreground"
          >
            Nenhum produto neste recorte.
          </p>
        </div>
        <p
          v-if="query && !stageRows.length"
          class="mt-3 text-center op-body text-muted-foreground"
        >
          Nenhum resultado para “{{ query.trim() }}”.
        </p>
      </template>
    </section>

    <!-- planejar -->
    <UiDialog
      :open="planRow != null"
      @update:open="
        (v) => {
          if (!v) {
            planRow = null;
            selectedPlannedPk = null;
          }
        }
      "
    >
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle
            >{{ PLAN_TITLE[planMode] }} ·
            {{ planRow ? rowLabel(planRow) : "" }}</UiDialogTitle
          >
          <UiDialogDescription>
            {{ planRow?.output_sku }} · {{ fullDateLabel(selectedDate) }}
            <template v-if="planRow?.suggestion">
              · sugestão {{ planRow.suggestion.quantity }}</template
            >
          </UiDialogDescription>
        </UiDialogHeader>
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
          <!-- Tile de fornada carrega referência e quantidade; é seleção de registro, não CTA. -->
          <button
            v-for="workOrder in planRow.planned_orders"
            :key="workOrder.pk"
            type="button"
            class="flex min-h-11 items-center justify-between rounded-md border px-3 py-2 text-left transition hover:bg-accent"
            @click="selectPlannedWorkOrder(workOrder)"
          >
            <span class="font-medium">#{{ workOrder.ref }}</span>
            <span class="tabular-nums text-muted-foreground"
              >{{ workOrder.planned_qty }} un.</span
            >
          </button>
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
          <!-- Stepper de 48px cerca o número central para operação rápida no tablet. -->
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            :disabled="planSource === 'suggested'"
            aria-label="Diminuir"
            @click="bump('plan', -1)"
          >
            −
          </button>
          <input
            ref="planQtyInput"
            v-model="planQty"
            type="text"
            inputmode="decimal"
            class="h-12 w-full rounded-md border bg-background text-center text-3xl font-bold tabular-nums outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            :readonly="planSource === 'suggested'"
            aria-label="Quantidade planejada"
            @keydown.enter.prevent="confirmPlan()"
          />
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            :disabled="planSource === 'suggested'"
            aria-label="Aumentar"
            @click="bump('plan', 1)"
          >
            +
          </button>
        </div>
        <UiDialogFooter>
          <UiButton
            type="button"
            variant="outline"
            @click="planRow = null"
          >
            Cancelar
          </UiButton>
          <UiButton
            type="button"
            :disabled="
              !planQty.trim() ||
              !planQtyValid ||
              !planActionAllowed ||
              planSubmitting ||
              (!!planRow?.planned_orders.length && !selectedPlannedOrder)
            "
            aria-keyshortcuts="Enter"
            @click="confirmPlan()"
          >
            {{
              planSubmitting
                ? "Confirmando…"
                : planMode === "new-batch"
                  ? "Confirmar novo lote"
                  : "Confirmar"
            }}
          </UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- Confirmar: o previsto abre o lote e segue para o Fechamento (evento interno: start) -->
    <UiDialog
      :open="startRow != null"
      @update:open="
        (v) => {
          if (!v) {
            startRow = null;
            selectedStartPk = null;
          }
        }
      "
    >
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>
            Quanto está previsto? ·
            {{ startRow ? rowLabel(startRow) : "" }}
          </UiDialogTitle>
          <UiDialogDescription
            >{{ startRow?.output_sku }} · esta quantidade abre o lote e segue
            para o Fechamento.</UiDialogDescription
          >
        </UiDialogHeader>
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
          <!-- Tile de fornada carrega referência e quantidade; é seleção de registro, não CTA. -->
          <button
            v-for="workOrder in startRow.planned_orders"
            :key="workOrder.pk"
            type="button"
            class="flex min-h-11 items-center justify-between rounded-md border px-3 py-2 text-left transition hover:bg-accent"
            @click="selectStartWorkOrder(workOrder)"
          >
            <span class="font-medium">#{{ workOrder.ref }}</span>
            <span class="tabular-nums text-muted-foreground"
              >{{ workOrder.planned_qty }} un.</span
            >
          </button>
        </div>
        <p v-if="selectedStartOrder" class="text-sm text-muted-foreground">
          Lote #{{ selectedStartOrder.ref }} · planejado
          {{ selectedStartOrder.planned_qty }}
        </p>
        <div v-if="selectedStartOrder" class="flex items-center gap-2">
          <!-- Stepper de 48px cerca o número central para operação rápida no tablet. -->
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Diminuir"
            @click="bump('start', -1)"
          >
            −
          </button>
          <input
            ref="startQtyInput"
            v-model="startQty"
            type="text"
            inputmode="decimal"
            class="h-12 w-full rounded-md border bg-background text-center text-3xl font-bold tabular-nums outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            aria-label="Quantidade prevista"
            @keydown.enter.prevent="confirmStart()"
          />
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Aumentar"
            @click="bump('start', 1)"
          >
            +
          </button>
        </div>
        <!-- Divergiu do planejado? A tela avisa e segue: é rendimento, não perda. -->
        <p
          v-if="selectedStartOrder && startDiverges"
          class="text-sm text-muted-foreground"
        >
          Diferente do planejado ({{ selectedStartOrder.planned_qty }}).
        </p>
        <UiDialogFooter>
          <UiButton
            type="button"
            variant="outline"
            @click="startRow = null"
          >
            Cancelar
          </UiButton>
          <UiButton
            type="button"
            :disabled="startSubmitting || !startReady"
            aria-keyshortcuts="Enter"
            @click="confirmStart()"
          >
            {{ startSubmitting ? "Confirmando…" : "Confirmar" }}
          </UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- lote aberto: conferência e cancelamento, sem etapas, sem gestão -->
    <UiDialog
      :open="startedRow != null"
      @update:open="
        (v) => {
          if (!v) {
            startedRow = null;
            selectedStartedPk = null;
            voidConfirming = false;
          }
        }
      "
    >
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle
            >Lote aberto ·
            {{ startedRow ? rowLabel(startedRow) : "" }}</UiDialogTitle
          >
          <UiDialogDescription>
            <template v-if="selectedStartedOrder">
              #{{ selectedStartedOrder.ref }} · {{ startedRow?.output_sku }} ·
              {{ selectedStartedOrder.started_qty }} un. previstas seguem para o
              Fechamento
            </template>
            <template v-else>Selecione o lote.</template>
          </UiDialogDescription>
        </UiDialogHeader>

        <div
          v-if="
            startedRow &&
            startedRow.started_orders.length > 1 &&
            !selectedStartedOrder
          "
          class="grid gap-2"
        >
          <!-- Tile de fornada carrega referência e quantidade; é seleção de registro, não CTA. -->
          <button
            v-for="workOrder in startedRow.started_orders"
            :key="workOrder.pk"
            type="button"
            class="flex min-h-11 items-center justify-between rounded-md border px-3 py-2 text-left transition hover:bg-accent"
            @click="selectedStartedPk = workOrder.pk"
          >
            <span class="font-medium">#{{ workOrder.ref }}</span>
            <span class="tabular-nums text-muted-foreground"
              >{{ workOrder.started_qty }} un.</span
            >
          </button>
        </div>

        <div v-if="voidConfirming" class="flex flex-col gap-2">
          <p
            class="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 p-2.5 text-sm text-warning"
          >
            <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
            <span
              >O lote volta atrás e o vínculo com pedidos é desfeito.</span
            >
          </p>
          <UiTextarea
            v-model="voidReason"
            :rows="2"
            placeholder="Motivo do cancelamento…"
            aria-label="Motivo do cancelamento"
          />
        </div>

        <UiDialogFooter class="gap-2">
          <UiButton
            v-if="selectedStartedOrder && !voidConfirming"
            type="button"
            class="mr-auto text-destructive hover:bg-destructive/10 hover:text-destructive"
            variant="outline"
            @click="voidConfirming = true"
          >
            Cancelar lote…
          </UiButton>
          <UiButton
            v-else-if="selectedStartedOrder"
            type="button"
            class="mr-auto"
            variant="destructive"
            @click="confirmVoid()"
          >
            Confirmar cancelamento
          </UiButton>
          <UiButton
            type="button"
            variant="outline"
            @click="
              startedRow = null;
              selectedStartedPk = null;
              voidConfirming = false;
            "
          >
            Voltar
          </UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- pedidos vinculados -->
    <UiDialog
      :open="commitmentsRow != null"
      @update:open="
        (v) => {
          if (!v) commitmentsRow = null;
        }
      "
    >
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle
            >{{ commitmentsRow ? rowCommittedUnits(commitmentsRow) : 0 }} un.
            comprometidas ·
            {{ commitmentsRow ? rowLabel(commitmentsRow) : "" }}</UiDialogTitle
          >
          <UiDialogDescription
            >{{ commitmentsRow?.output_sku }} · encomendas confirmadas que
            dependem desta produção.</UiDialogDescription
          >
        </UiDialogHeader>
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
              <UiBadge variant="outline" class="px-1.5 py-0 text-xs">{{
                commitment.status_label
              }}</UiBadge>
            </span>
            <span class="tabular-nums text-muted-foreground"
              >{{ commitment.qty_required }} un.</span
            >
          </li>
        </ul>
        <UiDialogFooter>
          <UiButton
            type="button"
            variant="outline"
            @click="commitmentsRow = null"
          >
            Fechar
          </UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <ShortageDialog
      :shortage="shortage"
      @update:open="
        (v) => {
          if (!v) closeShortage();
        }
      "
      @confirm="retryPlanWithForce"
      @review="reviewShortage"
    />
  </main>
</template>
