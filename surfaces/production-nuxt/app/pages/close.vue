<script setup lang="ts">
// Fechamento = o lote sai do forno já classificado (ADR-017 §9 / QC-FORNADA §5):
// painel de LOTES abertos do dia (o lote traz forno, horário e previsto; é o
// previsto que fecha o lote normal em poucos toques) e a tela de fechamento com
// partição (QcCloseScreen). A revisão do gestor sobre o lote já fechado mora na
// aba Qualidade (/quality). No formato das demais telas: ProductionHeader +
// rail; o miolo é o quiosque.
import type {
  QCOrderCardProjection,
  RecipeOptionProjection,
  ProductionShortageError,
} from "~/types/production";
import type { QcPartitionGroup } from "~/presentation/qc";
import { isStale, isoForOffset, matchLotCode } from "~/presentation/production";
import {
  periodAnchor,
  periodOfDay,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";
import {
  hasOpenDialogOutside,
  isEditableKeyboardTarget,
  isNativeActionTarget,
  productionContextKeysBlocked,
  resolveQuantityKeyboardShortcut,
} from "~/presentation/keyboard";

// A trilha da lista de lotes abertos (`OperatorRecordNav` no lote).
const CLOSE_LOTS_TRAIL = "production-close-lots";

const route = useRoute();
const routeDate = typeof route.query.date === "string" ? route.query.date : "";
const {
  kiosk,
  selectedDate,
  pending,
  error,
  submitting,
  refresh,
  finish,
  quickFinish,
} = useQcKiosk(routeDate);

// Tolerante a dado velho: poll falhou com painel na tela = chip de degradação
// (dado velho visível > painel em branco). No quiosque isso importa dobrado:
// fechar fornada com painel velho é fechar a fornada errada.
const stale = computed(() =>
  isStale({ error: !!error.value, hasData: !!kiosk.value }),
);

useHead({ title: "Fechamento" });

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

// ── Data: o "Período" do kit em Dia (Tipo 2). A fornada esquecida de ontem
// fecha por aqui, a um toque de ‹. Vazio é hoje (o servidor resolve), e o
// futuro não tem lote para fechar.
const todayISO = isoForOffset(0);
const period = computed<PeriodSelection>({
  get: () => periodOfDay("day", selectedDate.value, todayISO),
  set: (next) => {
    const day = periodAnchor(next, todayISO);
    selectedDate.value = day === todayISO ? "" : day;
  },
});
// O lote avulso (a exceção) mora no ⋯ do cabeçalho, fora de evidência.

// ── Navegação interna (painel ⇄ fechamento) ─────────────────────────────────
// O lote aberto mora na URL (`?lot=<pk>`, com o dia e a busca): o voltar do
// navegador volta ao painel, e o anterior e o próximo do lote são links de
// verdade. O lote avulso (receita sem previsto) não é registro: fica na tela.
const selectedOrder = ref<QCOrderCardProjection | null>(null);
const selectedRecipe = ref<RecipeOptionProjection | null>(null);
const recipePickerOpen = ref(false);

const routeLot = computed(() =>
  typeof route.query.lot === "string" ? route.query.lot : "",
);

function closeQuery(lot = ""): Record<string, string> {
  const next: Record<string, string> = {};
  if (selectedDate.value) next.date = selectedDate.value;
  const search = query.value.trim();
  if (search) next.q = search;
  if (lot) next.lot = lot;
  return next;
}
function lotLocation(lot: string) {
  return { path: "/close", query: closeQuery(lot) };
}

// Andar para outro lote (o ‹ › do `OperatorRecordNav`, ou o atalho) troca a tela
// inteira: com quantidades ou motivos digitados, pergunta antes de descartar. O
// voltar já pergunta dentro da tela, e sair para o painel (lote vazio) não passa aqui.
const closeScreen = ref<{ confirmDiscardChanges: (action: "leave" | "switch") => Promise<boolean> } | null>(null);
onBeforeRouteUpdate(async (to) => {
  const target = typeof to.query.lot === "string" ? to.query.lot : "";
  if (!target || target === routeLot.value || !closeScreen.value?.confirmDiscardChanges) return true;
  return closeScreen.value.confirmDiscardChanges("switch");
});

const matches = (order: QCOrderCardProjection) => {
  const q = query.value.trim().toLowerCase();
  if (!q) return true;
  return (
    order.recipe_name.toLowerCase().includes(q) ||
    order.output_sku.toLowerCase().includes(q) ||
    order.ref.toLowerCase().includes(q)
  );
};
const openOrders = computed(() =>
  (kiosk.value?.orders ?? []).filter((o) => !o.closed && matches(o)),
);
// A próxima a vencer ganha moldura: a primeira aberta (started primeiro).
const nextPk = computed(() => openOrders.value[0]?.pk ?? null);

function projectedAction(ref: string) {
  return kiosk.value?.actions.find((action) => action.ref === ref);
}

function finishAvailable(order: QCOrderCardProjection): boolean {
  return projectedAction(`finish:${order.pk}`)?.enabled === true;
}

function quickRecipeAvailable(recipe: RecipeOptionProjection): boolean {
  return projectedAction(`quick_finish:${recipe.pk}`)?.enabled === true;
}

function ovenFactAvailable(order: QCOrderCardProjection): boolean {
  return Boolean(
    projectedAction(`oven_arm:${order.pk}`)?.enabled ||
    projectedAction(`oven_conclude:${order.pk}`)?.enabled,
  );
}

// A trilha: os lotes que o painel mostra e que se fecham daqui, na ordem dele e
// com a busca da pessoa. Gravada só com o painel na tela (no lote, ela é a lista
// de onde a pessoa veio).
const { remember: rememberLots } = useRecordTrail(CLOSE_LOTS_TRAIL);
const trailFrom = computed(() => {
  const search = new URLSearchParams(closeQuery()).toString();
  return search ? `/close?${search}` : "/close";
});
watch(
  () =>
    [
      openOrders.value
        .filter(finishAvailable)
        .map((order) => String(order.pk))
        .join("\n"),
      trailFrom.value,
      routeLot.value,
    ] as const,
  ([ids, from, lot]) => {
    if (lot) return;
    rememberLots(ids ? ids.split("\n") : [], { from, label: "Lotes para finalizar" });
  },
  { immediate: true },
);

// O forno do lote aparece sempre, pelo nome (v3 celular a: "Forno 2 · …"): é
// por ele que o forneiro acha a assadeira.

function openOrder(order: QCOrderCardProjection) {
  if (!finishAvailable(order) || ovenFacts.isPending(order.pk)) return;
  void navigateTo(lotLocation(String(order.pk)));
}

function openOffPlan(recipe: RecipeOptionProjection) {
  if (!quickRecipeAvailable(recipe)) return;
  recipePickerOpen.value = false;
  selectedRecipe.value = recipe;
  selectedOrder.value = null;
}

// ── Etiqueta do lote ────────────────────────────────────────────────────────
const scannerOpen = ref(false);
function onLotCode(code: string) {
  const order = matchLotCode(code, openOrders.value);
  if (!order) {
    useSonner.error("Nenhum lote aberto com este código nesta data.");
    return;
  }
  scannerOpen.value = false;
  openOrder(order);
}
function seenAtLabel(order: QCOrderCardProjection): string {
  const seenAt = oven.get(ovenKey(order))?.seenAt;
  if (!seenAt) return "";
  return new Date(seenAt).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

// Sair do lote substitui a entrada dele no histórico: o voltar do navegador não
// reabre um lote que a pessoa já deixou (ou fechou).
function leaveLot() {
  void navigateTo(lotLocation(""), { replace: true });
}

function backToBoard() {
  selectedOrder.value = null;
  selectedRecipe.value = null;
  shortage.value = null;
  lastPayload.value = null;
  if (routeLot.value) leaveLot();
}

// ── Fechamento (com retry de force no shortage, como no restante do app) ────
const shortage = ref<ProductionShortageError | null>(null);
interface QcClosePayload {
  quantity: string;
  partition: QcPartitionGroup[];
  yield_deviation_confirmed: boolean;
  yield_deviation_reason: string;
  reason: string;
}
const lastPayload = ref<QcClosePayload | null>(null);

async function onConfirm(
  payload: QcClosePayload,
  force = false,
  reason = "",
  overrideProof = "",
) {
  lastPayload.value = payload;
  const closingOrder = selectedOrder.value;
  const result = closingOrder
    ? await finish(
        closingOrder.pk,
        ovenFacts.currentRev(closingOrder.pk, closingOrder.rev),
        payload.quantity,
        payload.partition,
        force,
        reason,
        payload.yield_deviation_confirmed,
        payload.yield_deviation_reason,
        overrideProof,
      )
    : selectedRecipe.value
      ? await quickFinish(
          selectedRecipe.value.pk,
          payload.quantity,
          payload.partition,
          force,
          reason,
          overrideProof,
        )
      : { ok: false };
  if (result.ok) {
    // Fornada fechada leva o timer junto — senão ele fica órfão no
    // localStorage e alarma depois, num card que nem existe mais.
    if (closingOrder) oven.clear(ovenKey(closingOrder));
    useSonner.success("Lote enviado para Qualidade (QC).");
    backToBoard();
    return;
  }
  if (result.shortage) shortage.value = result.shortage;
}

function retryWithForce(reason: string, overrideProof: string) {
  const payload = lastPayload.value;
  shortage.value = null;
  if (payload) onConfirm(payload, true, reason, overrideProof);
}

const screenTitle = computed(
  () => selectedOrder.value?.recipe_name ?? selectedRecipe.value?.name ?? "",
);
const screenSubtitle = computed(() => {
  const order = selectedOrder.value;
  if (!order) return selectedRecipe.value ? "Lote avulso" : "";
  // "CRO · lote #WO-118 · Forno 2" (v3 celular b).
  const bits = [
    order.output_sku,
    `lote #${order.ref}`,
    order.position_name || order.position_ref,
  ].filter(Boolean);
  return bits.join(" · ");
});
const screenPlanned = computed(() => {
  if (!selectedOrder.value) return null;
  const value = Number(selectedOrder.value.planned_qty);
  return Number.isFinite(value) ? Math.round(value) : null;
});
// A fornada real que entrou no forno (started): quando diverge do previsto,
// é ELA que ancora o fechamento — ver `ovenAnchor` em presentation/qc.ts.
const screenStarted = computed(() => {
  if (!selectedOrder.value?.started_qty) return null;
  const value = Number(selectedOrder.value.started_qty);
  return Number.isFinite(value) ? Math.round(value) : null;
});

// O quadradão "Finalizar" mostra a âncora, e a âncora É o previsto DESTA
// tela: o que entrou no forno é o que se espera que saia dele, salvo
// ocorrência. O plano da produção já cumpriu seu papel lá atrás; aqui ele
// não é mais informação, é ruído. Um número, um rótulo.
function cardAnchor(order: QCOrderCardProjection): string {
  return order.started_qty || order.planned_qty;
}

// Fornada esquecida não depende de memória: o aviso da tela leva ao dia
// pendente mais recente.
function shortDate(iso: string): string {
  const match = /^\d{4}-(\d{2})-(\d{2})$/.exec(iso);
  return match ? `${match[2]}/${match[1]}` : "";
}
const closeAlerts = computed<OperatorScreenAlert[]>(() => {
  const current = kiosk.value;
  if (!current || current.previous_open_count <= 0) return [];
  if (selectedOrder.value || selectedRecipe.value) return [];
  const count = current.previous_open_count;
  const day = shortDate(current.previous_open_date);
  return [
    {
      id: "previous-open",
      color: "warning",
      icon: "i-lucide-history",
      title: `${count} ${count === 1 ? "lote aberto" : "lotes abertos"} de dias anteriores`,
      action: {
        label: day ? `Ver os lotes de ${day}` : "Ver os lotes",
        onSelect: () => {
          selectedDate.value = current.previous_open_date;
        },
      },
    },
  ];
});

// ── Timer do forno: lembrete armado por fornada, com som ────────────────────
// A ferramenta ATIVA do forneiro para conferir/retirar — a ação de toda hora
// no rush: arma na enfornada, estende e marca Visto quando toca. Não confundir
// com o relógio de idade do lote (alertas), nem com concluir a fornada. É o
// mesmo mecanismo dos timers avulsos do cabeçalho (useFloorTimers): o forno
// só acrescenta o FATO declarado ao servidor.
const oven = useFloorTimers();
const quickFinishAvailable = computed(
  () =>
    selectedDate.value === "" &&
    (kiosk.value?.recipes ?? []).some((recipe) => quickRecipeAvailable(recipe)),
);
// "Lote avulso" (a fornada fora do plano) mora no ⋯ "Mais ações" do cabeçalho.
const closeActions = computed(() =>
  quickFinishAvailable.value
    ? [
        {
          label: "Lote avulso",
          icon: "i-lucide-plus",
          onSelect: () => {
            recipePickerOpen.value = true;
          },
        },
      ]
    : [],
);
// O countdown é local; o FATO (enfornou/retirou) é declarado ao servidor.
const ovenFacts = useOvenFacts(kiosk, refresh);
const ovenOrder = ref<QCOrderCardProjection | null>(null);
const ovenMinutes = ref("0");
const ovenFresh = ref(true);
const ovenKey = (order: QCOrderCardProjection) => String(order.pk);

// Timers vivem no localStorage — o servidor não os conhece. O primeiro render
// do cliente precisa BATER com o SSR (idle) e só então ligar: senão a classe
// do alarme fica presa no HTML do servidor (mismatch de hidratação não é
// re-aplicado pelo Vue).
const hydrated = ref(false);
onMounted(() => {
  hydrated.value = true;
  window.addEventListener("keydown", onTimerKeydown);
});
onBeforeUnmount(() => window.removeEventListener("keydown", onTimerKeydown));

// ── O lote da URL vira a tela de fechamento ─────────────────────────────────
// Entrar no lote é o gesto produtivo: se o forno ainda está declarado, abrir o
// fechamento declara "retirou" (o timer apenas lembra; o fato físico pertence à
// ação de finalizar a fornada, nunca ao Visto do alarme). Vale para o toque no
// painel, para o leitor de etiqueta, para o link e para o anterior/próximo. Só
// depois de montar: o SSR desenha o painel, e o cliente abre o lote.
let enteringLot = "";
async function syncLotFromRoute() {
  const lot = routeLot.value;
  if (!lot) {
    if (selectedOrder.value) {
      selectedOrder.value = null;
      shortage.value = null;
      lastPayload.value = null;
    }
    return;
  }
  if (!hydrated.value || !kiosk.value) return;
  if (selectedOrder.value && String(selectedOrder.value.pk) === lot) return;
  if (enteringLot === lot) return;
  const order = kiosk.value.orders.find(
    (item) => String(item.pk) === lot && !item.closed,
  );
  if (!order && pending.value) return;
  if (!order || !finishAvailable(order)) {
    // Lote fechado, de outro dia ou sem permissão: volta ao painel.
    selectedOrder.value = null;
    leaveLot();
    return;
  }
  enteringLot = lot;
  try {
    if (projectedAction(`oven_conclude:${order.pk}`)?.enabled === true) {
      const recorded = await ovenFacts.concluded(
        order.pk,
        ovenFacts.currentRev(order.pk, order.rev),
      );
      if (!recorded) {
        if (routeLot.value === lot) leaveLot();
        return;
      }
    }
    if (routeLot.value !== lot) return;
    oven.clear(ovenKey(order));
    ovenOrder.value = null;
    selectedRecipe.value = null;
    shortage.value = null;
    lastPayload.value = null;
    selectedOrder.value = order;
  } finally {
    if (enteringLot === lot) enteringLot = "";
  }
}
watch(
  [routeLot, () => kiosk.value, pending, hydrated],
  () => void syncLotFromRoute(),
);

type OvenMode = "idle" | "running" | "ringing" | "seen";
function ovenMode(order: QCOrderCardProjection): OvenMode {
  if (!hydrated.value) return "idle";
  const key = ovenKey(order);
  if (oven.isRinging(key)) return "ringing";
  if (oven.isSeen(key)) return "seen";
  return oven.get(key) ? "running" : "idle";
}
const dialogMode = computed<OvenMode>(() =>
  ovenOrder.value ? ovenMode(ovenOrder.value) : "idle",
);
const ovenFactPending = computed(() =>
  ovenOrder.value ? ovenFacts.isPending(ovenOrder.value.pk) : false,
);
const ovenFactError = computed(() =>
  ovenOrder.value ? ovenFacts.errorFor(ovenOrder.value.pk) : "",
);
// O diálogo (o elemento `role="dialog"`) carrega a marca da exclusão mútua com o
// timer avulso (`FloorTimerCreateDialog`); o `content` do NuxtModal é o que chega nele.
const TIMER_DIALOG_CONTENT: Record<string, unknown> = {
  "data-production-timer-dialog": "",
};
// As três linhas do teclado do timer: os dígitos e o +N ao lado de 3, 6 e 9.
const OVEN_PAD_ROWS = [
  { digits: [1, 2, 3], add: 1 },
  { digits: [4, 5, 6], add: 5 },
  { digits: [7, 8, 9], add: 10 },
] as const;

function openOven(order: QCOrderCardProjection) {
  if (!ovenFactAvailable(order)) return;
  ovenOrder.value = order;
  ovenMinutes.value = String(
    oven.get(ovenKey(order))?.minutes ?? oven.lastMinutes.value ?? 0,
  );
  ovenFresh.value = true;
}
function ovenDigit(digit: string) {
  const next = ovenFresh.value ? digit : `${ovenMinutes.value}${digit}`;
  ovenMinutes.value = String(Math.min(999, Number(next) || 0));
  ovenFresh.value = false;
}
function ovenBackspace() {
  ovenMinutes.value =
    ovenMinutes.value.length <= 1 ? "0" : ovenMinutes.value.slice(0, -1);
}
function ovenAdd(minutes: number) {
  const order = ovenOrder.value;
  if (!order) return;
  if (dialogMode.value === "idle") {
    ovenMinutes.value = String(
      (parseInt(ovenMinutes.value, 10) || 0) + minutes,
    );
    ovenFresh.value = true;
    return;
  }
  // Correndo, visto ou alarmando: soma ao vivo (visto/alarmando = rearma).
  oven.extend(ovenKey(order), minutes);
}
async function startOven() {
  const order = ovenOrder.value;
  const minutes = parseInt(ovenMinutes.value, 10);
  if (
    !order ||
    !(minutes >= 1) ||
    projectedAction(`oven_arm:${order.pk}`)?.enabled !== true
  )
    return;
  const recorded = await ovenFacts.armed(order.pk, order.rev, minutes);
  if (!recorded) return;
  oven.arm(ovenKey(order), minutes, {
    kind: "oven",
    label: order.recipe_name,
    sku: order.output_sku,
  });
  ovenOrder.value = null;
}
function markOvenSeen() {
  const order = ovenOrder.value;
  if (!order) return;
  oven.seen(ovenKey(order));
  ovenOrder.value = null;
}

function clearOvenMinutes() {
  ovenMinutes.value = "0";
  ovenFresh.value = true;
}

// O timer desenhado e o teclado físico alimentam o mesmo estado. Só o diálogo
// do timer captura estas teclas; nada age por baixo do lock do operador.
function onTimerKeydown(event: KeyboardEvent) {
  if (
    !ovenOrder.value ||
    event.repeat ||
    event.isComposing ||
    productionContextKeysBlocked() ||
    hasOpenDialogOutside("[data-production-timer-dialog]") ||
    isEditableKeyboardTarget(event.target)
  ) {
    return;
  }
  const shortcut = resolveQuantityKeyboardShortcut(event);
  if (!shortcut) return;
  if (
    shortcut.kind === "confirm" &&
    event.code !== "NumpadEnter" &&
    isNativeActionTarget(event.target)
  ) {
    return;
  }

  if (dialogMode.value === "idle") {
    event.preventDefault();
    if (shortcut.kind === "digit") ovenDigit(shortcut.digit);
    else if (shortcut.kind === "backspace") ovenBackspace();
    else if (shortcut.kind === "clear") clearOvenMinutes();
    else startOven();
    return;
  }
  if (dialogMode.value === "ringing" && shortcut.kind === "confirm") {
    event.preventDefault();
    markOvenSeen();
  }
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <ProductionHeader
      v-model:query="query"
      title="Fechamento"
      :count="openOrders.length"
      count-label="para finalizar"
      :progress="
        kiosk && kiosk.total_count > 0
          ? Math.round((kiosk.closed_count / kiosk.total_count) * 100)
          : null
      "
      :pending="pending"
      :stale="stale"
      search-label="filtrando os lotes"
      :actions="closeActions"
      :alerts="closeAlerts"
      @refresh="refresh"
    >
      <!-- Anterior e próximo DENTRO do painel de onde a pessoa veio. Aberto por
           link, sem trilha: o par não aparece. -->
      <template v-if="selectedOrder" #status>
        <OperatorRecordNav
          class="ms-auto"
          :trail="CLOSE_LOTS_TRAIL"
          :current="String(selectedOrder.pk)"
          :to="lotLocation"
          previous-label="Lote anterior"
          next-label="Próximo lote"
        />
      </template>
      <template v-if="!(selectedOrder || selectedRecipe)" #primary>
        <OperatorPeriodPicker
          v-model="period"
          compact
          class="[&_[data-period-today]]:hidden"
          :presets="['day']"
          :today="todayISO"
          :max="todayISO"
          label="Data dos lotes"
          align="end"
        />
      </template>
    </ProductionHeader>

    <!-- Tela de fechamento. -->
    <QcCloseScreen
      v-if="(selectedOrder || selectedRecipe) && kiosk"
      ref="closeScreen"
      :key="selectedOrder?.pk ?? `recipe-${selectedRecipe?.pk}`"
      :title="screenTitle"
      :subtitle="screenSubtitle"
      :planned="screenPlanned"
      :started="screenStarted"
      :grades="kiosk.grades"
      :defects="kiosk.defects"
      :submitting="submitting"
      @back="backToBoard"
      @confirm="onConfirm($event)"
    />

    <!-- Painel de lotes do dia. -->
    <div
      v-else
      class="mx-auto flex w-full max-w-4xl flex-col gap-3 px-3 py-3 md:px-4 md:py-4"
    >
      <div
        v-if="stale"
        role="status"
        aria-live="polite"
        class="inline-flex items-center gap-2 self-start rounded-full border border-warning/40 bg-warning/10 px-3 py-2 op-label font-semibold text-warning"
      >
        <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
        <span>Sem atualizar. Mostrando o último painel carregado.</span>
      </div>

      <p
        v-if="pending && !kiosk"
        class="py-10 text-center text-muted-foreground"
      >
        Carregando…
      </p>
      <p
        v-else-if="kiosk && !kiosk.orders.length"
        class="py-10 text-center text-muted-foreground"
      >
        Nenhum lote planejado para hoje.
      </p>
      <p
        v-else-if="kiosk && !openOrders.length"
        class="py-10 text-center text-muted-foreground"
      >
        Nenhum lote aguardando fechamento.
      </p>

      <p v-if="openOrders.length" class="op-eyebrow text-muted-foreground">
        Para finalizar <span class="tnum">{{ openOrders.length }}</span>
      </p>
      <div class="grid gap-2.5 lg:grid-cols-2">
        <!-- O toque no CARD abre o timer (a ação de toda hora); fechar a
             fornada é o botão quadrado do previsto, à direita. Alarmando, o
             card inteiro oscila em danger — visível do outro lado do fournil. -->
        <div
          v-for="order in openOrders"
          :key="order.pk"
          class="flex items-stretch justify-between gap-3 rounded-xl border border-border bg-card p-4 text-left transition"
          :class="[
            ovenFactAvailable(order) ? 'hover:bg-accent' : '',
            ovenMode(order) === 'ringing'
              ? 'qc-ringing border-destructive/60'
              : {
                  'border-2 border-primary': order.pk === nextPk,
                },
          ]"
          data-close-card
        >
          <div class="relative min-w-0 flex-1">
            <!-- O botão do timer cobre o lado do texto; o texto fica por cima,
                 sem capturar o toque. -->
            <NuxtButton
              v-if="ovenFactAvailable(order)"
              color="neutral"
              variant="ghost"
              class="absolute inset-0 z-0 h-auto w-full p-0 hover:bg-transparent"
              :aria-label="`Timer do forno de ${order.recipe_name}`"
              data-close-oven
              @click="openOven(order)"
            />
            <div class="pointer-events-none relative z-10">
              <p class="truncate op-title">
                {{ order.recipe_name }}
                <span class="font-mono op-micro font-normal text-muted-foreground">{{
                  order.output_sku
                }}</span>
              </p>
              <!-- "Forno 2 · aberto às 05:10 · 6 comprometidas" (R17/R18): o forno pelo
                   nome, sem o código do lote quebrando a linha (ele fica no ⋯ do
                   Finalizar e no leitor). -->
              <p class="op-label text-muted-foreground" data-close-card-line>
                <template v-if="order.position_name || order.position_ref"
                  >{{ order.position_name || order.position_ref }} ·
                </template>
                <template v-if="order.started_at_display"
                  >aberto às {{ order.started_at_display }}</template
                >
                <template v-else>ainda não aberto</template>
                <template
                  v-if="order.committed_qty && order.committed_qty !== '0'"
                >
                  ·
                  <span class="text-primary"
                    >{{ order.committed_qty }} comprometidas</span
                  >
                </template>
              </p>
              <p
                v-if="ovenFactAvailable(order)"
                class="mt-2 inline-flex min-h-12 items-center gap-2 rounded-lg border border-dashed border-border px-3"
                :class="
                  ovenMode(order) === 'ringing'
                    ? 'op-figure text-destructive'
                    : ovenMode(order) === 'idle'
                      ? 'op-title text-muted-foreground'
                      : ovenMode(order) === 'seen'
                        ? 'op-title border-solid border-success/40 bg-success/10 text-success'
                        : 'op-figure text-foreground'
                "
              >
                <Icon
                  :name="ovenMode(order) === 'seen' ? 'lucide:alarm-clock-check' : 'lucide:alarm-clock'"
                  class="size-5"
                />
                <template v-if="ovenMode(order) === 'ringing'"
                  >Tempo esgotado</template
                >
                <template v-else-if="ovenMode(order) === 'seen'"
                  >Visto<span
                    v-if="seenAtLabel(order)"
                    class="ml-2 op-micro font-normal text-muted-foreground"
                    >às {{ seenAtLabel(order) }}</span
                  ></template
                >
                <template v-else-if="ovenMode(order) === 'running'"
                  ><span class="tnum">{{ oven.remainingLabel(ovenKey(order)) }}</span
                  ><span class="ml-1 op-micro font-normal text-muted-foreground"
                    >restante</span
                  ></template
                >
                <template v-else>Iniciar timer</template>
              </p>
            </div>
          </div>
          <!-- Tile de 80px mostra quantidade e encerra a fornada com mão ocupada.
               O próximo lote tem o Finalizar cheio (a primária da tela); os outros,
               contornado (v3 celular a). -->
          <NuxtButton
            size="xl"
            variant="outline"
            :active="order.pk === nextPk"
            active-variant="solid"
            class="h-20 w-28 shrink-0 flex-col justify-center gap-1 self-center"
            :data-close-finish-next="order.pk === nextPk ? '' : undefined"
            :disabled="!finishAvailable(order) || ovenFacts.isPending(order.pk)"
            :aria-busy="ovenFacts.isPending(order.pk)"
            :aria-label="`Finalizar o lote de ${order.recipe_name}`"
            data-close-finish
            @click="openOrder(order)"
          >
            <span class="op-figure leading-none"
              >{{ cardAnchor(order) }} un.</span
            >
            <span class="op-eyebrow">{{
              ovenFacts.isPending(order.pk) ? "Abrindo…" : "Finalizar"
            }}</span>
          </NuxtButton>
        </div>
      </div>
    </div>

    <!-- "Ler etiqueta do lote" (R19): a câmera lê o QR da etiqueta de preparo e abre
         o Finalizar daquele lote. -->
    <div
      v-if="!(selectedOrder || selectedRecipe) && openOrders.length"
      class="mx-auto w-full max-w-4xl px-3 pb-4 md:px-4"
    >
      <NuxtButton
        color="neutral"
        variant="outline"
        size="xl"
        block
        icon="i-lucide-scan-qr-code"
        label="Ler etiqueta do lote"
        data-close-scan-label
        @click="scannerOpen = true"
      />
    </div>
    <LotLabelScanner v-model:open="scannerOpen" @code="onLotCode" />

    <!-- Lote avulso: lista de receitas, nasce sem previsto. -->
    <NuxtDrawer v-model:open="recipePickerOpen" title="Lote avulso">
      <template #body>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3" data-close-recipes>
          <NuxtButton
            v-for="recipe in kiosk?.recipes ?? []"
            :key="recipe.pk"
            color="neutral"
            variant="outline"
            size="xl"
            block
            class="h-auto justify-start whitespace-normal text-left"
            :label="recipe.name"
            :disabled="!quickRecipeAvailable(recipe)"
            @click="openOffPlan(recipe)"
          />
        </div>
      </template>
    </NuxtDrawer>

    <ShortageDialog
      :shortage="shortage"
      @update:open="
        (v: boolean) => {
          if (!v) shortage = null;
        }
      "
      @confirm="retryWithForce"
    />

    <!-- timer do forno (lembrete por fornada, com som); o X maior, pensando em
         touch: é a única saída sem ação. -->
    <NuxtModal
      :open="ovenOrder != null"
      :title="`Timer do forno · ${ovenOrder?.recipe_name ?? ''}`"
      description="Toca neste dispositivo."
      :close="{ size: 'xl' }"
      :content="TIMER_DIALOG_CONTENT"
      :ui="{ content: 'sm:max-w-sm' }"
      @update:open="
        (v: boolean) => {
          if (!v) ovenOrder = null;
        }
      "
    >
      <template #body>
        <div class="grid gap-3">
          <p
            v-if="ovenFactError"
            role="alert"
            class="rounded-md border border-destructive/40 bg-destructive/10 p-2.5 text-sm text-destructive"
          >
            {{ ovenFactError }} O timer local não foi alterado.
          </p>

          <!-- O processo físico não pausa. O mostrador informa; as únicas
               intervenções do timer são estender e marcar Visto. -->
          <div
            v-if="dialogMode === 'running'"
            class="flex h-20 w-full items-center justify-center gap-3 rounded-md border bg-background"
            role="timer"
            aria-label="Tempo restante"
          >
            <Icon name="lucide:alarm-clock" class="size-8 shrink-0" />
            <span class="text-4xl font-bold tabular-nums">
              {{ ovenOrder ? oven.remainingLabel(ovenKey(ovenOrder)) : "" }}
            </span>
          </div>
          <div
            v-else
            class="grid h-20 place-items-center rounded-md border text-center"
            :class="
              dialogMode === 'ringing'
                ? 'border-destructive/50 bg-destructive/10'
                : 'bg-background'
            "
          >
            <p
              v-if="dialogMode === 'ringing'"
              class="animate-pulse text-3xl font-bold text-destructive motion-reduce:animate-none"
            >
              Tempo esgotado
            </p>
            <p v-else-if="dialogMode === 'seen'" class="text-3xl font-bold">
              Visto
            </p>
            <p v-else class="text-4xl font-bold tabular-nums">
              {{ ovenMinutes
              }}<span class="ml-1 text-base font-medium text-muted-foreground"
                >min</span
              >
            </p>
          </div>

          <!-- Armando: teclado de 4 colunas, os +N ao lado de 3/6/9 (eles já
               substituem presets: 10 = C, +10) e o Iniciar fecha a grade. -->
          <div
            v-if="dialogMode === 'idle'"
            class="grid grid-cols-4 gap-1.5"
            role="group"
            aria-label="Minutos do timer"
            data-oven-pad
          >
            <template v-for="row in OVEN_PAD_ROWS" :key="row.add">
              <NuxtButton
                v-for="digit in row.digits"
                :key="digit"
                color="neutral"
                variant="outline"
                size="xl"
                block
                class="tabular-nums"
                :label="String(digit)"
                :aria-label="`Dígito ${digit}`"
                @click="ovenDigit(String(digit))"
              />
              <NuxtButton
                color="neutral"
                variant="ghost"
                size="xl"
                block
                class="tabular-nums"
                :label="`+${row.add}`"
                :aria-label="`Somar ${row.add} minutos`"
                @click="ovenAdd(row.add)"
              />
            </template>
            <NuxtButton
              color="neutral"
              variant="outline"
              size="xl"
              block
              label="C"
              aria-label="Limpar minutos"
              aria-keyshortcuts="C Delete"
              @click="clearOvenMinutes()"
            />
            <NuxtButton
              color="neutral"
              variant="outline"
              size="xl"
              block
              class="tabular-nums"
              label="0"
              aria-label="Dígito 0"
              @click="ovenDigit('0')"
            />
            <NuxtButton
              color="neutral"
              variant="outline"
              size="xl"
              block
              square
              icon="i-lucide-delete"
              aria-label="Apagar último dígito"
              @click="ovenBackspace()"
            />
            <NuxtButton
              size="xl"
              block
              :label="ovenFactPending ? 'Confirmando…' : 'Iniciar'"
              :disabled="ovenFactPending || !(parseInt(ovenMinutes, 10) >= 1)"
              aria-keyshortcuts="Enter"
              @click="startOven()"
            />
          </div>

          <!-- Correndo/alarmando/visto: +N ao vivo; Visto só silencia. -->
          <div
            v-else
            class="grid gap-1.5"
            :class="dialogMode === 'ringing' ? 'grid-cols-4' : 'grid-cols-3'"
          >
            <NuxtButton
              v-for="extra in [1, 5, 10]"
              :key="`add-${extra}`"
              color="neutral"
              variant="outline"
              size="xl"
              block
              class="tabular-nums"
              :label="`+${extra}`"
              :aria-label="`Somar ${extra} minutos`"
              @click="ovenAdd(extra)"
            />
            <NuxtButton
              v-if="dialogMode === 'ringing'"
              size="xl"
              block
              label="Visto"
              aria-keyshortcuts="Enter"
              @click="markOvenSeen()"
            />
          </div>
        </div>
      </template>
    </NuxtModal>
  </main>
</template>

<style scoped>
/* O card inteiro oscila em danger quando o alarme toca: visível do outro
   lado do fournil, sem depender de ler o texto. */
@keyframes qc-ring {
  0%,
  100% {
    background-color: var(--card);
  }
  50% {
    background-color: color-mix(in oklab, var(--destructive) 16%, var(--card));
  }
}
.qc-ringing {
  animation: qc-ring 1.1s ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  .qc-ringing {
    animation: none;
    box-shadow: inset 0 0 0 3px
      color-mix(in oklab, var(--destructive) 55%, transparent);
  }
}
</style>
