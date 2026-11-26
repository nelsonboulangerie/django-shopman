<script setup lang="ts">
// A GRADE por etapa — um motor, três lentes (refinos Pablo 2026-07-03):
//   PRODUTO | leitura | AÇÃO — cada lente tem UMA coluna de leitura e UMA de
//   ação com verbo no cabeçalho:
//   · plan (Planejamento): SUGERIDO  | PLANEJADO  (todos os SKUs);
//   · open (Produção):     PLANEJADO | PREVISTO   (só linhas com número).
// A finalização (PREVISTO → REALIZADO) mora na página /close, no quiosque de QC.
// A ação abre overlay com quantidade em stepper touch (+/−) e confirmação
// explícita; cada informe vira evento imutável (actor + timestamp → BI).
// Na Produção a ação é UMA só: "Confirmar" (o mesmo verbo do Planejamento)
// diz o previsto, que segue para a Finalização, já preenchido com o planejado
// (decisão Pablo 2026-09-16); o número fica na coluna Planejado, não no botão.
// A diferença para o planejado é rendimento da massa, não perda: fica nos dois
// números da ordem, sem pedir motivo; motivo se pede na Finalização, onde há
// produto pronto que pode sumir. Sem "iniciar", sem subetapas, sem máquina de
// estados: fermentação e afins são ferramenta (timer), nunca fluxo.
// Instruções específicas do SKU (peso de corte etc.) terão casa neste overlay
// (estudo de notação de pâtonnage pendente). Nomenclatura interna do sistema
// intacta (planned/started/finished) — as lentes são linguagem de UI.
import { nextTick, onMounted, type Ref } from "vue";

import LotCancelDialog from "./LotCancelDialog.vue";
import LotCommitmentsDialog from "./LotCommitmentsDialog.vue";
import LotStartPanel from "./LotStartPanel.vue";
import PlanAdjustDialog from "./PlanAdjustDialog.vue";
import PlanLens from "./PlanLens.vue";

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
  outsizedQuantityWarning,
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
import type { ActiveFilters, FilterDimension } from "../../../operator-kit/app/types/filters";
import type {
  ProductionKDSCardProjection,
  ProductionMatrixRowProjection,
  ProductionShortageError,
  WorkOrderCardProjection,
} from "~/types/production";
import type {
  AuthorizeFormulaDeviationInput,
  AuthorizeFormulaDeviationResponse,
} from "~/composables/useProductionKds";
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
  voidOrder,
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
// A data mora na URL (beta 05/11): recarregar o Planejamento de sábado não
// pode voltar para hoje e deixar alguém planejar no dia errado. Só no
// Planejamento: o tablet do chão fica dias aberto, e recarregar (atualização do
// app) tem de voltar para hoje, nunca para o dia que alguém espiou.
const router = useRouter();
const rail = useProductionRail();
// O dia acompanha o gesto de trocar de etapa. A URL do chão continua sem o
// dia espiado, para uma atualização do tablet voltar para hoje.
watch(selectedDate, (date) => { rail.value.viewedDate = date; }, { immediate: true });
watch(selectedDate, (date) => {
  if (props.stage !== "plan") return;
  if (route.query.date === date) return;
  void router.replace({ query: { ...route.query, date } });
});
// Trocou o dia e a resposta ainda é do dia anterior: nada de cabeçalho de um
// dia sobre a lista de outro, nem botão ativo nesse meio-tempo (beta 05/11).
const switchingDay = computed(
  () =>
    pending.value &&
    !!board.value?.selected_date &&
    board.value.selected_date !== selectedDate.value,
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

// Linhas por lente: Planejamento vê TODOS os SKUs; Produção só quem tem
// número relevante (higiene de foco na bancada).
const stageRows = computed<ProductionMatrixRowProjection[]>(() => {
  let base = rows.value.filter((r) => matchesRowQuery(r, query.value));
  if (baseFilter.value) {
    base = base.filter((r) =>
      r.base_usages.some((usage) => usage.output_sku === baseFilter.value),
    );
  }
  // O lote fechado continua na lista (P2-13): sem ele a linha sumia ao fechar e o
  // progresso do dia encolhia ("5 de 8" virava "4 de 7").
  if (props.stage === "open") {
    return base.filter(
      (r) => r.planned_qty !== "0" || r.started_qty !== "0" || r.finished_qty !== "0",
    );
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
// Os campos de quantidade moram nos diálogos (`PlanAdjustDialog`, `LotStartPanel`):
// cada um expõe `focusQty`, que leva o foco ao `<input>` do `NuxtInput`.
type QtyField = { focusQty: () => void } | null;
const planDialog = ref<QtyField>(null);
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
// O previsto tem duas formas (o painel encaixado e o diálogo); só uma está na tela.
const startPanel = ref<QtyField>(null);
const startModal = ref<QtyField>(null);
function focusQty(...fields: Ref<QtyField>[]) {
  void nextTick(() => fields.forEach((field) => field.value?.focusQty()));
}
const startSubmitting = ref(false);
const selectedStartPk = ref<number | null>(null);
const startedRow = ref<ProductionMatrixRowProjection | null>(null);
const selectedStartedPk = ref<number | null>(null);
const voidReason = ref("");
const voidConfirming = ref(false);
const voidSubmitting = ref(false);
const oldDoughOrder = ref<WorkOrderCardProjection | null>(null);
// Recusa do servidor no registro de massa velha, campo a campo (beta 05/11: o
// toast genérico ficava atrás do modal e nenhum campo era marcado).
const oldDoughErrors = ref<
  Partial<Record<"quantity" | "expiryDate" | "note" | "form", string>>
>({});
const deviationCard = ref<ProductionKDSCardProjection | null>(null);
const deviationResult = ref<AuthorizeFormulaDeviationResponse | null>(null);
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
const selectedOldDoughAction = computed(() => {
  const workOrder = selectedStartedOrder.value;
  return workOrder
    ? kds.actionFor(`register_old_dough:${workOrder.pk}`)
    : undefined;
});
const selectedStartedKdsCard = computed(() => {
  const workOrder = selectedStartedOrder.value;
  return workOrder
    ? kds.cards.value.find((card) => card.pk === workOrder.pk)
    : undefined;
});
const selectedDeviationAction = computed(() => {
  const workOrder = selectedStartedOrder.value;
  return workOrder
    ? kds.actionFor(`authorize_formula_deviation:${workOrder.pk}`)
    : undefined;
});

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
// Rendimento diferente só se avisa; um zero a mais se confere. Passou de 3x o
// planejado, o aviso diz o número e Confirmar só libera depois de "O número
// está certo" (botão no aviso, longe do Confirmar: toque duplo não passa).
// Mexeu no número, a conferência volta a valer.
function acknowledgeStartOutsized() {
  startOutsizedAcknowledged.value = startQty.value.trim();
}
const startOutsized = computed(() => {
  const wo = selectedStartOrder.value;
  return wo ? outsizedQuantityWarning(startQty.value, wo.planned_qty) : null;
});
const startOutsizedAcknowledged = ref<string | null>(null);
const startNeedsDoubleCheck = computed(
  () =>
    !!startOutsized.value &&
    startOutsizedAcknowledged.value !== startQty.value.trim(),
);
watch(startRow, () => {
  startOutsizedAcknowledged.value = null;
});
// O mesmo cuidado no planejar: a referência é a sugestão do dia.
const planOutsized = computed(() =>
  planRow.value
    ? outsizedQuantityWarning(planQty.value, planRow.value.suggestion?.quantity, "a sugestão")
    : null,
);
const planOutsizedAcknowledged = ref<string | null>(null);
const planNeedsDoubleCheck = computed(
  () =>
    !!planOutsized.value &&
    planOutsizedAcknowledged.value !== planQty.value.trim(),
);
watch(planRow, () => {
  planOutsizedAcknowledged.value = null;
});
function acknowledgePlanOutsized() {
  planOutsizedAcknowledged.value = planQty.value.trim();
}
// Zero no ajuste tira o lote do plano: o botão diz isso, sem código secreto.
const planRemoves = computed(
  () => planMode.value === "adjust" && !!planQty.value.trim() && qtyNumber(planQty.value) === 0,
);
// Tirar do plano é cancelar o lote: leva o motivo de quem decidiu (#3400).
const planRemoveReason = ref("");
watch(planRow, () => {
  planRemoveReason.value = "";
});

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
  const value = Number.isInteger(next)
    ? String(next)
    : next.toFixed(3).replace(/\.?0+$/, "");
  target.value = field === "start" ? startDisplay(value) : value;
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
    focusQty(planDialog);
  }
}

function selectPlannedWorkOrder(workOrder: WorkOrderCardProjection) {
  selectedPlannedPk.value = workOrder.pk;
  if (planSource.value === "manual") planQty.value = workOrder.planned_qty;
  focusQty(planDialog);
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
// finalização foi para planejar, o foco é do diálogo de planejamento.
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
  if (planNeedsDoubleCheck.value) return;
  planSubmitting.value = true;
  try {
    const res = await submitPlan(row, {
      quantity: planQty.value.trim(),
      source: planSource.value,
      workOrder: selectedPlannedOrder.value,
      newBatch: planMode.value === "new-batch",
      reason: planRemoves.value ? planRemoveReason.value.trim() : undefined,
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
    /** O motivo de quem tirou o lote do plano (zero sobre lote existente). */
    reason?: string;
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
    ...(opts.reason ? { reason: opts.reason } : {}),
  };
  const label = opts.newBatch ? "Novo lote planejado" : "Planejado";
  const successMessage =
    qtyNumber(opts.quantity) === 0
      ? `${rowLabel(row)} saiu do plano.`
      : `${label}: ${rowLabel(row)} × ${opts.quantity}`;
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
  startQty.value = startDisplay(selectedStartOrder.value?.planned_qty ?? "");
  if (selectedStartPk.value != null) {
    focusQty(startPanel, startModal);
  }
}

function selectStartWorkOrder(workOrder: WorkOrderCardProjection) {
  selectedStartPk.value = workOrder.pk;
  startQty.value = startDisplay(workOrder.planned_qty);
  focusQty(startPanel, startModal);
}

async function confirmStart() {
  if (startSubmitting.value) return;
  const row = startRow.value;
  const wo = selectedStartOrder.value;
  if (!row || !wo || !startReady.value) return;
  if (startNeedsDoubleCheck.value) return;
  startSubmitting.value = true;
  try {
    const res = await start(
      row.output_sku,
      wo.pk,
      wo.rev,
      startQty.value.trim().replace(",", "."),
    );
    if (res.ok) {
      startRow.value = null;
      selectedStartPk.value = null;
      kds.refresh();
      useSonner.success(
        `Lote aberto: ${rowLabel(row)} × ${formatQtyUnit(startQty.value.trim(), row.output_unit)}`,
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
    focusQty(startPanel, startModal);
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
  focusQty(planDialog);
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
  voidReason.value = "";
  kds.refresh();
}

async function confirmVoid() {
  const row = startedRow.value;
  const wo = selectedStartedOrder.value;
  const reason = voidReason.value.trim();
  if (!row || !wo || !reason || voidSubmitting.value) return;
  // A ação vem da matriz do dia, que traz o lote planejado e o aberto (#2957). A
  // recusa (permissão, números velhos, outra tela mexeu) chega pelo aviso do guarda,
  // com a causa e o "Atualizar os números", e o diálogo fica aberto.
  voidSubmitting.value = true;
  let res: Awaited<ReturnType<typeof voidOrder>>;
  try {
    res = await voidOrder(row.output_sku, wo.pk, wo.rev, reason);
  } finally {
    voidSubmitting.value = false;
  }
  if (res.ok) {
    startedRow.value = null;
    voidConfirming.value = false;
    voidReason.value = "";
    refresh();
    // O lote aberto também sai do quadro da bancada.
    kds.refresh();
    useSonner.success(`Lote cancelado: ${rowLabel(row)}`);
  }
}

function openOldDoughRegistration() {
  const workOrder = selectedStartedOrder.value;
  if (!workOrder || !selectedOldDoughAction.value?.enabled) return;
  oldDoughOrder.value = workOrder;
  startedRow.value = null;
  selectedStartedPk.value = null;
}

async function registerOldDough(input: {
  quantity: string;
  unit: "g" | "kg";
  expiryDate: string;
  positionRef?: string;
  note?: string;
}) {
  const workOrder = oldDoughOrder.value;
  if (!workOrder) return;
  oldDoughErrors.value = {};
  const result = await kds.registerOldDough(workOrder.pk, workOrder.rev, input);
  if (result.fieldErrors) {
    const { quantity, expiry_date, note, ...rest } = result.fieldErrors;
    const other = Object.values(rest)[0];
    oldDoughErrors.value = {
      quantity,
      expiryDate: expiry_date,
      note,
      form: other ?? (quantity || expiry_date || note ? undefined : "Corrija os campos e tente de novo."),
    };
    return;
  }
  if (!result.ok) return;
  oldDoughOrder.value = null;
  refresh();
  useSonner.success(
    result.data?.batch_ref
      ? `Massa velha registrada: lote ${result.data.batch_ref}`
      : "Massa velha registrada.",
  );
}

function openFormulaDeviation() {
  const card = selectedStartedKdsCard.value;
  if (
    !card ||
    !card.formula_limits.length ||
    !selectedDeviationAction.value?.enabled
  )
    return;
  deviationCard.value = card;
  deviationResult.value = null;
  startedRow.value = null;
  selectedStartedPk.value = null;
}

async function authorizeFormulaDeviation(input: AuthorizeFormulaDeviationInput) {
  const card = deviationCard.value;
  if (!card) return;
  const result = await kds.authorizeFormulaDeviation(card.pk, card.rev, input);
  if (!result.ok || !result.data) return;
  deviationResult.value = result.data;
  refresh();
  useSonner.success("Desvio autorizado. A fórmula do lote foi recalculada.");
}

function closeFormulaDeviation() {
  deviationCard.value = null;
  deviationResult.value = null;
}

// ── ⋯ da linha aberta (R12) e "pressione e segure" no tablet deitado (R13) ──
// As ações da linha são DADOS, uma fonte só: o ⋯ (`OperatorMoreMenu`) e o menu de
// contexto da linha (`NuxtContextMenu`, que abre ao segurar a linha no toque e no
// clique direito no mouse) desenham a mesma lista.
function openRowMenu(row: ProductionMatrixRowProjection): OperatorMoreMenuItem[][] {
  const main: OperatorMoreMenuItem[] = [{ type: "label", label: rowLabel(row) }];
  if (row.started_orders.length)
    main.push({
      label: "Detalhes do lote",
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
  voidReason.value = "";
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
// Com o painel encaixado a lista estreita, e ela encolhe por colunas, nunca pelo nome
// (P1-06, `EV/02`): a Situação vira um ponto antes do nome, o Planejado desce para a
// linha do SKU ("· 42 planejadas") e, abaixo de 1280 px, a ação da linha é só o ícone.
// Ficam Produto, Previsto e Ação.
// Sem o painel, as colunas de número e a da ação têm a largura do que mostram ("A
// confirmar", o número, "Confirmar" e o ⋯): fixas, para alinhar de uma linha para a
// outra, e justas, para o nome do produto caber a 1024 px (#2959: com 236 px na ação,
// sobravam 76 px para o produto, e o nome quebrava no meio da palavra).
// No toque (tablet deitado ou em pé, celular), todo alvo das linhas tem 44 px (P1-25).
// A suíte desenha botão em 32 px (dono, 09/10/2026); o chão de luva e farinha é a
// opção maior do app, sem mexer no kit.
const FLOOR_TARGETS =
  "pointer-coarse:[&_button]:min-h-11 pointer-coarse:[&_button]:min-w-11";
const dockedCompact = computed(() => docked.value && screen.belowXl.value);
const openCols = computed(() =>
  docked.value
    ? "lg:grid-cols-[minmax(0,1fr)_64px_100px] xl:grid-cols-[minmax(0,1fr)_72px_200px] lg:gap-x-3"
    : "lg:grid-cols-[minmax(0,1fr)_120px_96px_96px_156px]",
);

// A situação da linha da Produção: a confirmar, aberto ou fechado. O lote fechado
// fica na lista com o previsto que teve (P2-13).
type OpenSituation = "pending" | "opened" | "closed";
function openSituation(row: ProductionMatrixRowProjection): OpenSituation {
  if (openRowPending(row)) return "pending";
  if (row.started_orders.length) return "opened";
  return "closed";
}
const OPEN_SITUATION: Record<
  OpenSituation,
  { label: string; color: "warning" | "success" | "neutral"; dot: string }
> = {
  pending: { label: "A confirmar", color: "warning", dot: "bg-warning" },
  opened: { label: "Aberto", color: "success", dot: "bg-success" },
  closed: { label: "Fechado", color: "neutral", dot: "bg-muted-foreground" },
};
// O previsto da linha soma os lotes abertos e os fechados: fechar não apaga o número.
function rowForecastQty(row: ProductionMatrixRowProjection): string {
  const total = [...row.started_orders, ...row.finished_orders].reduce(
    (sum, order) => sum + qtyNumber(order.started_qty || "0"),
    0,
  );
  return total ? String(Number(total.toFixed(3))) : "0";
}

// O teclado da tela do previsto. Peça conta inteira; massa e creme (g, kg, l) aceitam
// vírgula, com até três casas (P1-22, o lado da abertura). O campo guarda a vírgula
// que a pessoa vê; o envio troca por ponto.
const START_COUNT_UNITS = new Set(["", "un", "un.", "und", "pc", "pç", "unidade"]);
const startDecimal = computed(
  () => !START_COUNT_UNITS.has((startRow.value?.output_unit ?? "").trim().toLowerCase()),
);
function startDisplay(value: string): string {
  return value.replace(".", ",");
}
const startPadFresh = ref(true);
function startDigit(key: string) {
  const current = startPadFresh.value ? "" : startQty.value;
  startPadFresh.value = false;
  if (key === ",") {
    if (!startDecimal.value || current.includes(",")) return;
    startQty.value = `${current || "0"},`;
    return;
  }
  const [whole = "", fraction] = `${current}${key}`.split(",");
  if (fraction !== undefined) {
    if (fraction.length > 3) return;
    startQty.value = `${whole},${fraction}`;
    return;
  }
  startQty.value = String(Math.min(99999, Number(whole) || 0));
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

// Progresso do dia, no cabeçalho: "4 de 28 planejados" (Planejamento) ou "5 de 8
// abertos" (Produção), com a barra do quanto o dia andou. Conta produtos (linhas),
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
// O filtro único da suíte (dono, 04/11/2026): a situação da linha e a ficha-base são
// as dimensões do painel, cada uma de escolha única, com a contagem ao lado. Some o
// seletor de ficha-base paralelo; a Situação mora na faixa da mesa e no painel do
// celular, nunca nos dois na mesma forma de tela.
const panelDimensions = computed<FilterDimension[]>(() => [
  {
    id: "state",
    label: "Situação",
    type: "single-select",
    options:
      props.stage === "plan"
        ? PLAN_FILTERS.filter((filter) => filter.key !== "all").map((filter) => ({
            value: filter.key,
            label: filter.label,
            count: planGroups.value.counts[filter.key],
          }))
        : OPEN_FILTERS.filter((filter) => filter.key !== "all").map((filter) => ({
            value: filter.key,
            label: filter.label,
            count: openGroups.value.counts[filter.key],
          })),
  },
  ...(baseOptions.value.length
    ? [
        {
          id: "base",
          label: "Base",
          type: "single-select" as const,
          options: baseOptions.value.map((base) => ({
            value: base.output_sku,
            label: base.name,
            count: base.count,
          })),
        },
      ]
    : []),
]);
// Na mesa a Situação é a faixa (abaixo): o painel não a repete.
const deskPanelDimensions = computed(() =>
  panelDimensions.value.filter((dimension) => dimension.id !== "state"),
);
// Os recortes de todo dia na mesa: os filtros rápidos do kit, um de cada vez, com a
// contagem ao lado.
const planFilterTabs = computed(() =>
  PLAN_FILTERS.map((filter) => ({
    key: filter.key,
    label: filter.label,
    count: planGroups.value.counts[filter.key],
  })),
);
const openFilterTabs = computed(() =>
  OPEN_FILTERS.map((filter) => ({
    key: filter.key,
    label: filter.label,
    count: openGroups.value.counts[filter.key],
  })),
);
const panelFilters = computed<ActiveFilters>({
  get: () => {
    const state = props.stage === "plan" ? planFilter.value : openFilter.value;
    return {
      ...(state !== "all" ? { state: [state] } : {}),
      ...(baseFilter.value ? { base: [baseFilter.value] } : {}),
    };
  },
  set: (next) => {
    const state = next.state?.[0] ?? "all";
    if (props.stage === "plan") planFilter.value = state as PlanFilter;
    else openFilter.value = state as OpenFilter;
    baseFilter.value = next.base?.[0] ?? "";
  },
});

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
  // Um zero a mais na linha não planeja direto: abre o diálogo, que mostra o
  // número contra a sugestão e pede a conferência (beta 05/11: 99.999 passou).
  const draft = draftOf(row).trim();
  if (outsizedQuantityWarning(draft, row.suggestion?.quantity, "a sugestão")) {
    openPlan(row, "manual");
    if (planRow.value === row) planQty.value = draft;
    return;
  }
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
      label: `Situação: ${quick.label}`,
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
  if (switchingDay.value) return "";
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
  return wo ? `#${wo.ref} · ${sku}` : "Selecione o lote.";
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
      <!-- O filtro único da suíte (dono, 04/11/2026), um lugar por recorte em cada forma
           de tela. Na mesa, a Situação é a faixa de um toque com a contagem (P1 de 02/10)
           e o painel leva a Base, com "Filtros (n)" e os chips com ×. No celular, o ícone
           na linha do chão, com o número no canto, e a Situação entra no painel. Sem
           favoritos por ora: o quadro não está no registro de telas do servidor
           (`saved_views.SCREENS`). -->
      <template #filter-panel="{ compact }">
        <OperatorFilterPanel
          v-model="panelFilters"
          :dimensions="compact ? panelDimensions : deskPanelDimensions"
          :trigger="compact ? 'icon' : 'button'"
          :chips="!compact"
          :data-stage-filters="compact ? 'compact' : 'desk'"
        />
      </template>
      <template #filters>
        <!-- Os recortes de todo dia, na mesa: abas em pílula com a contagem. -->
        <OperatorQuickFilters
          v-if="stage === 'plan'"
          :model-value="planFilter"
          :items="planFilterTabs"
          label="Recorte do Planejamento"
          data-plan-filters
          @update:model-value="(value) => (planFilter = (Array.isArray(value) ? value[0] : value) as PlanFilter)"
        />
        <OperatorQuickFilters
          v-else
          :model-value="openFilter"
          :items="openFilterTabs"
          label="Recorte da Produção"
          data-open-filters
          @update:model-value="(value) => (openFilter = (Array.isArray(value) ? value[0] : value) as OpenFilter)"
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
    <section
      class="min-h-0 min-w-0 flex-1 overflow-auto px-3 pt-3 pb-4 md:px-4"
      :class="switchingDay ? 'pointer-events-none opacity-50' : ''"
      :aria-busy="switchingDay"
      :data-switching-day="switchingDay ? '' : undefined"
    >
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
          :class="FLOOR_TARGETS"
          data-plan-table
        >
          <div
            class="hidden h-10 items-center gap-4 border-b border-border bg-muted/60 px-4 op-eyebrow text-muted-foreground lg:grid lg:grid-cols-[minmax(0,1fr)_180px_140px_160px] xl:grid-cols-[minmax(0,1fr)_250px_168px_176px]"
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
            class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-4 py-3 last:border-b-0 lg:grid lg:min-h-[62px] lg:grid-cols-[minmax(0,1fr)_180px_140px_160px] xl:grid-cols-[minmax(0,1fr)_250px_168px_176px] lg:py-2"
            :class="
              reasonSku === row.output_sku
                ? 'bg-primary/5 shadow-[inset_0_0_0_2px_var(--primary)]'
                : ''
            "
            data-plan-row
            :data-sku="row.output_sku"
          >
            <!-- Produto: nome, SKU e o chip das encomendas. No tablet (1024 a 1279 px) as
                 colunas da sugestão, da quantidade e da ação ficam com a largura do que
                 mostram (até 145, 136 e 158 px, medidos), e o nome ganha o resto: com as
                 larguras da mesa, sobravam 92 px e o nome acabava em reticências (#2966). -->
            <div
              class="flex w-full min-w-0 items-center gap-2.5 lg:w-auto"
              data-row-product
            >
              <!-- O nome é o que o padeiro lê: quebra em 2 linhas antes de
                   cortar (beta 05/11: "Kuro Pan…" e "Kuro Pan Burger" iguais). -->
              <p
                class="min-w-0 line-clamp-2 break-normal hyphens-none op-title"
                :title="rowLabel(row)"
                data-row-name
              >
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

            <!-- Sugestão: o número, o "?" colado nele e, no máximo, um sinal. A conta
                 mora no "?", que abre ancorado na linha (UX-P2, L3). -->
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
                      <NuxtButton
                        :ref="(el) => rememberReasonTrigger(row.output_sku, el)"
                        color="neutral"
                        variant="ghost"
                        icon="i-lucide-circle-help"
                        square
                        class="-ml-1.5 shrink-0"
                        :ui="{ leadingIcon: reasonSku === row.output_sku ? '' : 'text-muted-foreground' }"
                        :active="reasonSku === row.output_sku"
                        active-color="primary"
                        active-variant="outline"
                        data-plan-reason-trigger
                        aria-haspopup="dialog"
                        :aria-expanded="reasonSku === row.output_sku"
                        :aria-label="`Por que ${row.suggestion.quantity} de ${rowLabel(row)}?`"
                        @click="toggleReason(row)"
                      />
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

          <PlanLens
            :clean-count="planGroups.clean.length"
            :manual-count="planGroups.manual.length"
            :clean-summary="cleanSummary"
            :manual-summary="manualSummary"
            :can-plan-clean-set="canPlanCleanSet"
            :bulk-submitting="bulkSubmitting"
            :inline-busy="inlineSubmitting != null"
            @expand-clean="expandClean = true"
            @expand-manual="expandManual = true"
            @plan-clean="planCleanSet()"
          />

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

        <!-- ── Produção ─────────────────────────────────────────────────────── -->
        <div
          v-else
          class="overflow-hidden rounded-lg border border-border bg-card"
          :class="FLOOR_TARGETS"
          data-open-table
        >
          <div
            class="hidden h-10 items-center gap-4 border-b border-border bg-muted/60 px-4 op-eyebrow text-muted-foreground lg:grid"
            :class="openCols"
            aria-hidden="true"
          >
            <span>Produto</span>
            <template v-if="!docked">
              <span>Situação</span>
              <span class="text-right">{{ lens.read.visible ? lens.read.label : "" }}</span>
            </template>
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
              class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 border-b border-border px-4 py-2.5 last:border-b-0 lg:min-h-14 lg:py-2"
              :class="[
                openCols,
                openSituation(row) === 'opened' ? 'bg-success/5' : '',
                docked && startRow?.output_sku === row.output_sku
                  ? 'shadow-[inset_4px_0_0_var(--primary)] bg-primary/5'
                  : '',
              ]"
              data-open-row
              :data-sku="row.output_sku"
            >
              <div class="min-w-0" data-row-product>
                <!-- Nome em até 2 linhas, nunca "Croissa…" no tablet deitado. Quebra por
                     palavra, nunca no meio dela ("Coelhinh o", #2959); o que não couber
                     nas 2 linhas termina em reticências. -->
                <!-- Sem a coluna Situação (celular, tablet em pé, painel encaixado), a
                     situação é o ponto antes do nome. -->
                <div class="flex items-start gap-2">
                  <span
                    class="mt-[0.45em] size-2.5 shrink-0 rounded-full"
                    :class="[OPEN_SITUATION[openSituation(row)].dot, docked ? '' : 'lg:hidden']"
                    data-open-situation-dot
                  >
                    <span class="sr-only">{{ OPEN_SITUATION[openSituation(row)].label }}</span>
                  </span>
                  <p
                    class="line-clamp-2 min-w-0 break-normal hyphens-none op-title"
                    :title="rowLabel(row)"
                    data-row-name
                  >
                    {{ rowLabel(row) }}
                  </p>
                </div>
                <p class="mt-0.5 flex items-center gap-1.5 op-micro text-muted-foreground">
                  <span class="truncate font-mono">{{ row.output_sku }}</span>
                  <!-- Celular, tablet em pé e painel encaixado: sem a coluna Planejado, o
                       número vem aqui. -->
                  <span
                    v-if="row.planned_qty !== '0' && openSituation(row) === 'pending' && lens.read.visible"
                    class="shrink-0 tabular-nums"
                    :class="docked ? '' : 'lg:hidden'"
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
              <template v-if="!docked">
                <span class="hidden lg:inline-flex">
                  <NuxtBadge
                    :color="OPEN_SITUATION[openSituation(row)].color"
                    :label="OPEN_SITUATION[openSituation(row)].label"
                  />
                </span>
                <span
                  v-if="lens.read.visible"
                  class="hidden text-right text-lg font-semibold tabular-nums lg:block"
                  :class="row.planned_qty === '0' ? 'text-muted-foreground' : ''"
                  >{{ row.planned_qty === "0" ? "—" : formatQty(row.planned_qty, row.output_unit) }}</span
                >
                <span v-else class="hidden lg:block" />
              </template>
              <!-- Previsto: o número abre a conferência e o cancelamento do lote aberto. -->
              <span v-if="lens.action.visible" class="hidden justify-end lg:flex">
                <span
                  v-if="rowForecastQty(row) !== '0'"
                  class="inline-flex items-center gap-1.5 text-lg font-semibold tabular-nums"
                  >{{ formatQty(rowForecastQty(row), row.output_unit) }}
                  <Icon name="lucide:circle-check" class="size-4 text-success"
                /></span>
                <span
                  v-else
                  class="text-lg font-semibold tabular-nums text-muted-foreground"
                  >—</span
                >
              </span>
              <span v-else class="hidden lg:block" />
              <div class="flex items-center justify-end gap-1.5">
                <!-- No celular e no tablet em pé o previsto vem junto da ação. -->
                <span
                  v-if="rowForecastQty(row) !== '0' && lens.action.visible"
                  class="inline-flex h-8 items-center gap-1.5 px-1 text-base font-semibold tabular-nums lg:hidden"
                  data-open-started-compact
                  >{{ formatQty(rowForecastQty(row), row.output_unit) }}
                  <Icon name="lucide:circle-check" class="size-4 text-success"
                /></span>
                <!-- Confirmando: o painel encaixado está aberto nesta linha (tablet deitado). -->
                <NuxtButton
                  v-if="docked && startRow?.output_sku === row.output_sku"
                  size="xl"
                  :square="dockedCompact"
                  :class="dockedCompact ? 'size-11 justify-center' : ''"
                  trailing-icon="i-lucide-chevron-right"
                  :label="dockedCompact ? undefined : 'Confirmando'"
                  :aria-label="`Confirmando ${rowLabel(row)}: fechar o painel`"
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
                  :square="dockedCompact"
                  :class="dockedCompact ? 'size-11 justify-center' : ''"
                  icon="i-lucide-check"
                  :label="dockedCompact ? undefined : 'Confirmar'"
                  :disabled="isBusy(row.output_sku)"
                  :aria-label="`Confirmar ${rowLabel(row)}`"
                  data-open-confirm
                  @click="openStart(row)"
                />
                <!-- ⋯ da linha; no tablet deitado o mesmo menu abre ao segurar a linha. -->
                <OperatorMoreMenu
                  :label="`Mais ações de ${rowLabel(row)}`"
                  :items="openRowMenu(row)"
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
          Pressione e segure uma linha: Detalhes do lote · Ver encomendas · Cancelar lote.
        </p>
        <p
          v-if="query && !stageRows.length"
          class="mt-3 text-center op-body text-muted-foreground"
        >
          Nenhum resultado para “{{ query.trim() }}”.
        </p>
      </template>
    </section>

    <LotStartPanel
      v-if="docked && startRow"
      ref="startPanel"
      v-model:qty="startQty"
      variant="panel"
      :row="startRow"
      :selected-pk="selectedStartPk"
      :selected-order="selectedStartOrder"
      :submitting="startSubmitting"
      :ready="startReady"
      :outsized="startOutsized"
      :needs-double-check="startNeedsDoubleCheck"
      :diverges="startDiverges"
      :decimal="startDecimal"
      @close="
        startRow = null;
        selectedStartPk = null;
      "
      @select="selectStartWorkOrder"
      @bump="(delta: number) => bump('start', delta)"
      @confirm="confirmStart()"
      @acknowledge="acknowledgeStartOutsized"
      @digit="startDigit"
      @backspace="startBackspace"
      @clear="startClear"
    />
    </div>

    <PlanAdjustDialog
      ref="planDialog"
      v-model:qty="planQty"
      v-model:remove-reason="planRemoveReason"
      :row="planRow"
      :title="`${PLAN_TITLE[planMode]} · ${planRow ? rowLabel(planRow) : ''}`"
      :description="planDescription"
      :mode="planMode"
      :selected-order="selectedPlannedOrder"
      :source="planSource"
      :outsized="planOutsized"
      :needs-double-check="planNeedsDoubleCheck"
      :submitting="planSubmitting"
      :qty-valid="planQtyValid"
      :action-allowed="planActionAllowed"
      :removes="planRemoves"
      @close="
        planRow = null;
        selectedPlannedPk = null;
      "
      @cancel="planRow = null"
      @select="selectPlannedWorkOrder"
      @bump="(delta: number) => bump('plan', delta)"
      @confirm="confirmPlan()"
      @acknowledge="acknowledgePlanOutsized"
    />

    <LotStartPanel
      ref="startModal"
      v-model:qty="startQty"
      variant="modal"
      :open="startRow != null && !docked"
      :row="startRow"
      :selected-pk="selectedStartPk"
      :selected-order="selectedStartOrder"
      :submitting="startSubmitting"
      :ready="startReady"
      :outsized="startOutsized"
      :needs-double-check="startNeedsDoubleCheck"
      :diverges="startDiverges"
      :decimal="startDecimal"
      @close="
        startRow = null;
        selectedStartPk = null;
      "
      @select="selectStartWorkOrder"
      @bump="(delta: number) => bump('start', delta)"
      @confirm="confirmStart()"
      @acknowledge="acknowledgeStartOutsized"
      @digit="startDigit"
      @backspace="startBackspace"
      @clear="startClear"
    />

    <LotCancelDialog
      v-model:void-reason="voidReason"
      :row="startedRow"
      :title="startedRow ? rowLabel(startedRow) : 'Detalhes do lote'"
      :description="startedDescription"
      :orders="startedDialogOrders"
      :selected-order="selectedStartedOrder"
      :void-confirming="voidConfirming"
      :void-submitting="voidSubmitting"
      :old-dough-action="selectedOldDoughAction"
      :deviation-action="selectedDeviationAction"
      :kds-card="selectedStartedKdsCard"
      @close="
        startedRow = null;
        selectedStartedPk = null;
        voidConfirming = false;
      "
      @select="(pk: number) => (selectedStartedPk = pk)"
      @ask-void="voidConfirming = true"
      @confirm-void="confirmVoid()"
      @register-old-dough="openOldDoughRegistration"
      @authorize-deviation="openFormulaDeviation"
    />

    <RegisterOldDoughDialog
      :open="oldDoughOrder != null"
      :work-order-label="
        oldDoughOrder
          ? `${oldDoughOrder.recipe_name} · lote #${oldDoughOrder.ref}`
          : 'Lote'
      "
      :position-ref="oldDoughOrder?.position_ref"
      :busy="oldDoughOrder ? kds.isBusy(oldDoughOrder.pk) : false"
      :field-errors="oldDoughErrors"
      @update:open="(open: boolean) => { if (!open) { oldDoughOrder = null; oldDoughErrors = {}; } }"
      @submit="registerOldDough"
    />

    <AuthorizeFormulaDeviationDialog
      :open="deviationCard != null"
      :work-order-label="
        deviationCard
          ? `${deviationCard.recipe_name} · lote #${deviationCard.ref}`
          : 'Lote'
      "
      :limits="deviationCard?.formula_limits ?? []"
      :result="deviationResult"
      :busy="deviationCard ? kds.isBusy(deviationCard.pk) : false"
      @update:open="(open: boolean) => { if (!open) closeFormulaDeviation() }"
      @submit="authorizeFormulaDeviation"
    />

    <LotCommitmentsDialog
      :row="commitmentsRow"
      @close="commitmentsRow = null"
    />

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
