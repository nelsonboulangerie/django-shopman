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
import {
  hasOpenDialogOutside,
  isEditableKeyboardTarget,
  isNativeActionTarget,
  productionContextKeysBlocked,
  resolveQuantityKeyboardShortcut,
} from "~/presentation/keyboard";

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
const selectedOrder = ref<QCOrderCardProjection | null>(null);
const selectedRecipe = ref<RecipeOptionProjection | null>(null);
const recipePickerOpen = ref(false);

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

// O forno do lote aparece sempre, pelo nome (v3 celular a: "Forno 2 · …"): é
// por ele que o forneiro acha a assadeira.

async function openOrder(order: QCOrderCardProjection) {
  if (!finishAvailable(order) || ovenFacts.isPending(order.pk)) return;
  // O timer apenas lembra. O fato físico "retirou do forno" pertence à ação
  // produtiva de finalizar a fornada, nunca ao Visto do alarme.
  if (projectedAction(`oven_conclude:${order.pk}`)?.enabled === true) {
    const recorded = await ovenFacts.concluded(
      order.pk,
      ovenFacts.currentRev(order.pk, order.rev),
    );
    if (!recorded) return;
  }
  oven.clear(ovenKey(order));
  ovenOrder.value = null;
  selectedOrder.value = order;
  selectedRecipe.value = null;
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
  void openOrder(order);
}
function seenAtLabel(order: QCOrderCardProjection): string {
  const seenAt = oven.get(ovenKey(order))?.seenAt;
  if (!seenAt) return "";
  return new Date(seenAt).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function backToBoard() {
  selectedOrder.value = null;
  selectedRecipe.value = null;
  shortage.value = null;
  lastPayload.value = null;
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
      @refresh="refresh"
    >
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

      <!-- Fornada esquecida não depende de memória: o painel avisa e o toque
           vai direto ao dia pendente mais recente. -->
      <!-- Aviso inteiro é acionável para levar ao dia pendente; não é um CTA isolado. -->
      <button
        v-if="kiosk && kiosk.previous_open_count > 0"
        type="button"
        class="flex min-h-12 items-center gap-2 rounded-lg border border-warning/50 bg-warning/10 px-4 py-3 text-left op-label font-semibold text-warning transition hover:bg-warning/20"
        @click="selectedDate = kiosk.previous_open_date"
      >
        <Icon name="lucide:history" class="size-4 shrink-0" />
        <span class="flex-1">
          <b class="tabular-nums">{{ kiosk.previous_open_count }}</b>
          {{
            kiosk.previous_open_count === 1 ? "lote aberto" : "lotes abertos"
          }}
          de dias anteriores. Toque para ver.
        </span>
        <Icon name="lucide:chevron-right" class="size-4 shrink-0" />
      </button>

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
            ovenFactAvailable(order) ? 'cursor-pointer hover:bg-accent' : '',
            ovenMode(order) === 'ringing'
              ? 'qc-ringing border-destructive/60'
              : {
                  'border-2 border-primary': order.pk === nextPk,
                },
          ]"
        >
          <component
            :is="ovenFactAvailable(order) ? 'button' : 'div'"
            class="min-w-0 flex-1 rounded-md text-left focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
            v-bind="
              ovenFactAvailable(order)
                ? {
                    type: 'button',
                    'aria-label': `Timer do forno de ${order.recipe_name}`,
                  }
                : {}
            "
            @click="ovenFactAvailable(order) && openOven(order)"
          >
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
          </component>
          <!-- Hover invertido: contraste garantido mesmo com o card em accent. -->
          <!-- Tile de 80px mostra quantidade e encerra a fornada com mão ocupada. -->
          <!-- O próximo lote tem o Finalizar cheio (a primária da tela); os outros,
               contornado (v3 celular a). -->
          <button
            type="button"
            class="group flex h-20 w-28 shrink-0 flex-col items-center justify-center gap-1 self-center rounded-lg border transition active:translate-y-px"
            :class="[
              order.pk === nextPk
                ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90'
                : 'border-primary/40 bg-primary/10 hover:border-primary hover:bg-primary hover:text-primary-foreground',
              {
                'cursor-not-allowed opacity-50 hover:border-border hover:bg-background hover:text-foreground':
                  !finishAvailable(order) || ovenFacts.isPending(order.pk),
              },
            ]"
            :data-close-finish-next="order.pk === nextPk ? '' : undefined"
            :disabled="!finishAvailable(order) || ovenFacts.isPending(order.pk)"
            :aria-busy="ovenFacts.isPending(order.pk)"
            :aria-label="`Finalizar o lote de ${order.recipe_name}`"
            @click.stop="openOrder(order)"
          >
            <span class="op-figure leading-none"
              >{{ cardAnchor(order) }} un.</span
            >
            <span
              class="op-eyebrow group-hover:text-primary-foreground"
              :class="order.pk === nextPk ? 'text-primary-foreground' : 'text-foreground'"
              >{{
                ovenFacts.isPending(order.pk) ? "Abrindo…" : "Finalizar"
              }}</span
            >
          </button>
        </div>
      </div>
    </div>

    <!-- "Ler etiqueta do lote" (R19): a câmera lê o QR da etiqueta de preparo e abre
         o Finalizar daquele lote. -->
    <div
      v-if="!(selectedOrder || selectedRecipe) && openOrders.length"
      class="mx-auto w-full max-w-4xl px-3 pb-4 md:px-4"
    >
      <button
        type="button"
        class="flex min-h-14 w-full items-center justify-center gap-2.5 rounded-xl border border-border bg-card op-title transition hover:bg-accent"
        data-close-scan-label
        @click="scannerOpen = true"
      >
        <Icon name="lucide:scan-qr-code" class="size-5" />
        Ler etiqueta do lote
      </button>
    </div>
    <LotLabelScanner v-model:open="scannerOpen" @code="onLotCode" />

    <!-- Lote avulso: lista de receitas, nasce sem previsto. -->
    <UiSheet
      :open="recipePickerOpen"
      @update:open="(v: boolean) => (recipePickerOpen = v)"
    >
      <UiSheetContent side="bottom" title="Lote avulso">
        <template #content>
          <div class="grid grid-cols-2 gap-2 px-4 pb-6 sm:grid-cols-3">
            <!-- Receitas são tiles de escolha para criar o lote avulso, não CTAs repetidos. -->
            <button
              v-for="recipe in kiosk?.recipes ?? []"
              :key="recipe.pk"
              type="button"
              class="rounded-md border bg-card px-3 py-2.5 text-left font-medium transition hover:bg-accent"
              :disabled="!quickRecipeAvailable(recipe)"
              @click="openOffPlan(recipe)"
            >
              {{ recipe.name }}
            </button>
          </div>
        </template>
      </UiSheetContent>
    </UiSheet>

    <ShortageDialog
      :shortage="shortage"
      @update:open="
        (v: boolean) => {
          if (!v) shortage = null;
        }
      "
      @confirm="retryWithForce"
    />

    <!-- timer do forno (lembrete por fornada, com som) -->
    <UiDialog
      :open="ovenOrder != null"
      @update:open="
        (v: boolean) => {
          if (!v) ovenOrder = null;
        }
      "
    >
      <UiDialogContent
        class="sm:max-w-sm"
        data-production-timer-dialog
        hide-close
      >
        <!-- X maior, pensando em touch: é a única saída sem ação. -->
        <template #close>
          <UiDialogClose
            class="absolute right-2 top-2 grid size-11 place-items-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
            aria-label="Fechar"
          >
            <Icon name="lucide:x" class="size-6" />
          </UiDialogClose>
        </template>
        <UiDialogHeader>
          <UiDialogTitle
            >Timer do forno · {{ ovenOrder?.recipe_name }}</UiDialogTitle
          >
          <UiDialogDescription>Toca neste dispositivo.</UiDialogDescription>
        </UiDialogHeader>

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
          class="flex h-20 w-full items-center justify-center gap-3 rounded-md border bg-background transition hover:bg-accent active:translate-y-px"
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

        <!-- Armando: numpad de 4 colunas — os +N moram ao lado de 3/6/9 (eles
             já substituem presets: 10 = C, +10) e o Iniciar fecha a grade. -->
        <div
          v-if="dialogMode === 'idle'"
          class="grid grid-cols-4 gap-1.5"
          role="group"
          aria-label="Minutos do timer"
        >
          <!-- Teclado de forno mantém a matriz e o feedback tátil; é intencionalmente customizado. -->
          <template
            v-for="row in [
              [1, 2, 3],
              [4, 5, 6],
              [7, 8, 9],
            ]"
            :key="row[0]"
          >
            <button
              v-for="digit in row"
              :key="digit"
              type="button"
              class="rounded-md border bg-card py-2.5 text-lg font-semibold tabular-nums transition hover:bg-accent active:translate-y-px"
              :aria-label="`Dígito ${digit}`"
              @click="ovenDigit(String(digit))"
            >
              {{ digit }}
            </button>
            <button
              type="button"
              class="rounded-md border border-dashed bg-card py-2.5 text-base font-semibold tabular-nums text-muted-foreground transition hover:bg-accent hover:text-foreground active:translate-y-px"
              :aria-label="`Somar ${row[2] === 3 ? 1 : row[2] === 6 ? 5 : 10} minutos`"
              @click="ovenAdd(row[2] === 3 ? 1 : row[2] === 6 ? 5 : 10)"
            >
              +{{ row[2] === 3 ? 1 : row[2] === 6 ? 5 : 10 }}
            </button>
          </template>
          <button
            type="button"
            class="rounded-md border bg-card py-2.5 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            aria-label="Limpar minutos"
            aria-keyshortcuts="C Delete"
            @click="clearOvenMinutes()"
          >
            C
          </button>
          <button
            type="button"
            class="rounded-md border bg-card py-2.5 text-lg font-semibold tabular-nums transition hover:bg-accent active:translate-y-px"
            aria-label="Dígito 0"
            @click="ovenDigit('0')"
          >
            0
          </button>
          <button
            type="button"
            class="grid place-items-center rounded-md border bg-card py-2.5 transition hover:bg-accent active:translate-y-px"
            aria-label="Apagar último dígito"
            @click="ovenBackspace()"
          >
            <Icon name="lucide:delete" class="size-5" />
          </button>
          <button
            type="button"
            :disabled="ovenFactPending || !(parseInt(ovenMinutes, 10) >= 1)"
            aria-keyshortcuts="Enter"
            class="rounded-md border border-transparent bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 active:translate-y-px disabled:opacity-50"
            @click="startOven()"
          >
            {{ ovenFactPending ? "Confirmando…" : "Iniciar" }}
          </button>
        </div>

        <!-- Correndo/alarmando/visto: +N ao vivo; Visto só silencia. -->
        <div
          v-else
          class="grid gap-1.5"
          :class="dialogMode === 'ringing' ? 'grid-cols-4' : 'grid-cols-3'"
        >
          <!-- Extensões do timer repetem a geometria do teclado acima. -->
          <button
            v-for="extra in [1, 5, 10]"
            :key="`add-${extra}`"
            type="button"
            class="rounded-md border bg-card py-2.5 text-base font-semibold tabular-nums transition hover:bg-accent active:translate-y-px"
            @click="ovenAdd(extra)"
          >
            +{{ extra }}
          </button>
          <button
            v-if="dialogMode === 'ringing'"
            type="button"
            class="rounded-md border border-transparent bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 active:translate-y-px"
            aria-keyshortcuts="Enter"
            @click="markOvenSeen()"
          >
            Visto
          </button>
        </div>
      </UiDialogContent>
    </UiDialog>
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
