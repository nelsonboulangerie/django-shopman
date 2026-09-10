<script setup lang="ts">
// Expedição = fechamento de fornada (ADR-017 §9 / QC-FORNADA §5). A fornada
// sai do forno já classificada: painel de ORDENS do dia (a ordem traz forno,
// horário e previsto — é o previsto que fecha a fornada normal em poucos
// toques) e a tela de fechamento com partição (QcCloseScreen). No formato
// das demais telas: ProductionHeader + rail; o miolo é o quiosque.
import type {
  QCOrderCardProjection,
  RecipeOptionProjection,
  ProductionShortageError,
} from "~/types/production";
import type { QcPartitionGroup } from "~/presentation/qc";
import { isStale } from "~/presentation/production";
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
  correctQuality,
} = useQcKiosk(routeDate);

// Tolerante a dado velho: poll falhou com painel na tela = chip de degradação
// (dado velho visível > painel em branco). No quiosque isso importa dobrado:
// fechar fornada com painel velho é fechar a fornada errada.
const stale = computed(() =>
  isStale({ error: !!error.value, hasData: !!kiosk.value }),
);

useHead({ title: "Expedição · Produção" });

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

// ── Data: Hoje · Outra data (a fornada esquecida de ontem fecha por aqui) ───
const isCustomDate = computed(() => selectedDate.value !== "");
const customDateInput = ref<HTMLInputElement | null>(null);
function openCustomDate() {
  customDateInput.value?.showPicker?.();
  customDateInput.value?.focus();
}

// Menu ⋯ do painel — a exceção mora aqui, fora de evidência.
const menuOpen = ref(false);

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
const closedOrders = computed(() =>
  (kiosk.value?.orders ?? []).filter((o) => o.closed && matches(o)),
);
// A próxima a vencer ganha moldura: a primeira aberta (started primeiro).
const nextPk = computed(() => openOrders.value[0]?.pk ?? null);

function projectedAction(ref: string) {
  return kiosk.value?.actions.find((action) => action.ref === ref);
}

function finishAvailable(order: QCOrderCardProjection): boolean {
  return projectedAction(`finish:${order.pk}`)?.enabled === true;
}

function correctionAvailable(order: QCOrderCardProjection): boolean {
  return projectedAction(`correct_qc:${order.pk}`)?.enabled === true;
}

function correctionPartition(order: QCOrderCardProjection): QcPartitionGroup[] {
  return order.partition;
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

// Posição/forno só quando as fornadas ABERTAS divergem: igual em tudo (ou só
// nas fechadas, que nem mostram posição) é ruído puro.
const showPosition = computed(
  () =>
    new Set(
      (kiosk.value?.orders ?? [])
        .filter((o) => !o.closed)
        .map((o) => o.position_ref)
        .filter(Boolean),
    ).size > 1,
);

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

function openCorrection(order: QCOrderCardProjection) {
  if (!correctionAvailable(order)) return;
  selectedOrder.value = order;
  selectedRecipe.value = null;
}

function openOffPlan(recipe: RecipeOptionProjection) {
  if (!quickRecipeAvailable(recipe)) return;
  recipePickerOpen.value = false;
  selectedRecipe.value = recipe;
  selectedOrder.value = null;
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
  const correcting = Boolean(closingOrder?.closed);
  const result = closingOrder
    ? correcting
      ? await correctQuality(
          closingOrder.pk,
          closingOrder.rev,
          payload.partition,
          payload.reason,
        )
      : await finish(
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
    if (closingOrder && !correcting) oven.clear(ovenKey(closingOrder));
    useSonner.success(
      correcting ? "Qualidade corrigida." : "Quantidade concluída.",
    );
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
const screenMode = computed<"close" | "correct">(() =>
  selectedOrder.value?.closed ? "correct" : "close",
);
const screenInitialPartition = computed(() =>
  selectedOrder.value?.closed ? correctionPartition(selectedOrder.value) : [],
);
const screenSubtitle = computed(() => {
  const order = selectedOrder.value;
  if (!order) return selectedRecipe.value ? "Fornada avulsa" : "";
  const bits = [
    order.output_sku,
    showPosition.value ? order.position_ref : "",
    order.started_at_display,
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

// O quadradão "Confirmar" mostra a âncora — e a âncora É o produzido DESTA
// tela: o que entrou no forno é o que se espera que saia dele, salvo
// ocorrência. O plano da produção já cumpriu seu papel lá atrás; aqui ele
// não é mais informação, é ruído. Um número, um rótulo.
function cardAnchor(order: QCOrderCardProjection): string {
  return order.started_qty || order.planned_qty;
}

// ── Timer do forno: lembrete armado por fornada, com som ────────────────────
// A ferramenta ATIVA do forneiro para conferir/retirar — a ação de toda hora
// no rush: arma na enfornada, estende e marca Visto quando toca. Não confundir
// com o relógio de idade do lote (alertas), nem com concluir a fornada.
const oven = useOvenTimers();
const quickFinishAvailable = computed(
  () =>
    !isCustomDate.value &&
    (kiosk.value?.recipes ?? []).some((recipe) => quickRecipeAvailable(recipe)),
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
  oven.arm(ovenKey(order), minutes);
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
  <main class="flex min-h-screen flex-col">
    <ProductionHeader
      v-model:query="query"
      title="Expedição"
      :count="kiosk?.closed_count"
      :count-label="`de ${kiosk?.total_count ?? 0} concluídas`"
      :progress="
        kiosk && kiosk.total_count > 0
          ? Math.round((kiosk.closed_count / kiosk.total_count) * 100)
          : null
      "
      :pending="pending"
      @refresh="refresh"
    />

    <!-- Tela de fechamento. -->
    <QcCloseScreen
      v-if="(selectedOrder || selectedRecipe) && kiosk"
      :key="`${screenMode}-${selectedOrder?.pk ?? `recipe-${selectedRecipe?.pk}`}`"
      :title="screenTitle"
      :subtitle="screenSubtitle"
      :planned="screenPlanned"
      :started="screenStarted"
      :grades="kiosk.grades"
      :defects="kiosk.defects"
      :mode="screenMode"
      :initial-partition="screenInitialPartition"
      :submitting="submitting"
      @back="backToBoard"
      @confirm="onConfirm($event)"
    />

    <!-- Painel de fornadas do dia. -->
    <div v-else class="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-4">
      <div class="flex items-center justify-between gap-3">
        <!-- Data: mesmo padrão de chips das outras telas do backstage. -->
        <div
          class="flex items-center gap-1 rounded-lg border bg-background p-0.5"
          role="group"
          aria-label="Data das fornadas"
        >
          <button
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="
              !isCustomDate
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            "
            @click="selectedDate = ''"
          >
            Hoje
          </button>
          <button
            type="button"
            class="relative rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="
              isCustomDate
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            "
            @click="openCustomDate"
          >
            {{ isCustomDate ? kiosk?.selected_date_display : "Outra data" }}
            <input
              ref="customDateInput"
              v-model="selectedDate"
              type="date"
              class="absolute inset-0 cursor-pointer opacity-0"
              aria-label="Escolher a data das fornadas"
              tabindex="-1"
            />
          </button>
        </div>

        <UiPopover
          v-if="quickFinishAvailable"
          :open="menuOpen"
          @update:open="(v: boolean) => (menuOpen = v)"
        >
          <UiPopoverTrigger as-child>
            <button
              type="button"
              class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground"
              aria-label="Mais ações"
            >
              <Icon name="lucide:ellipsis-vertical" class="size-4" />
            </button>
          </UiPopoverTrigger>
          <UiPopoverContent align="end" :side-offset="6" class="w-52 p-1.5">
            <button
              type="button"
              class="flex w-full items-center gap-2 rounded px-2 py-2 text-left text-sm transition hover:bg-accent"
              @click="
                menuOpen = false;
                recipePickerOpen = true;
              "
            >
              <Icon name="lucide:plus" class="size-4 text-muted-foreground" />
              Fornada avulsa
            </button>
          </UiPopoverContent>
        </UiPopover>
      </div>

      <div
        v-if="stale"
        role="status"
        aria-live="polite"
        class="flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm font-medium text-amber-700 dark:text-amber-300"
      >
        <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
        <span>Sem atualizar. Mostrando o último painel carregado.</span>
      </div>

      <!-- Fornada esquecida não depende de memória: o painel avisa e o toque
           vai direto ao dia pendente mais recente. -->
      <button
        v-if="kiosk && kiosk.previous_open_count > 0"
        type="button"
        class="flex items-center gap-2 rounded-lg border border-warning/50 bg-warning/10 px-4 py-3 text-left text-sm text-amber-700 transition hover:bg-warning/20 dark:text-amber-300"
        @click="selectedDate = kiosk.previous_open_date"
      >
        <Icon name="lucide:history" class="size-4 shrink-0" />
        <span>
          <b class="tabular-nums">{{ kiosk.previous_open_count }}</b>
          {{
            kiosk.previous_open_count === 1
              ? "fornada aberta"
              : "fornadas abertas"
          }}
          de dias anteriores. Toque para ver.
        </span>
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
        Nenhuma fornada planejada para hoje.
      </p>

      <div class="grid gap-2">
        <!-- O toque no CARD abre o timer (a ação de toda hora); fechar a
             fornada é o botão quadrado do previsto, à direita. Alarmando, o
             card inteiro oscila em danger — visível do outro lado do fournil. -->
        <div
          v-for="order in openOrders"
          :key="order.pk"
          class="flex items-stretch justify-between gap-3 rounded-lg border bg-card p-4 text-left transition"
          :class="[
            ovenFactAvailable(order) ? 'cursor-pointer hover:bg-accent' : '',
            ovenMode(order) === 'ringing'
              ? 'qc-ringing border-destructive/60'
              : {
                  'border-primary ring-2 ring-primary/30': order.pk === nextPk,
                },
          ]"
        >
          <component
            :is="ovenFactAvailable(order) ? 'button' : 'div'"
            class="min-w-0 flex-1 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
            <p class="truncate text-base font-semibold">
              {{ order.recipe_name }}
            </p>
            <p class="truncate text-sm text-muted-foreground">
              {{ order.output_sku }}
              <template v-if="showPosition && order.position_ref">
                · {{ order.position_ref }}</template
              >
              <template v-if="order.started_at_display">
                · produzida às {{ order.started_at_display }}</template
              >
              <template v-else> · ainda não produzida</template>
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
              class="mt-2 flex items-center gap-2 text-lg font-semibold tabular-nums"
              :class="
                ovenMode(order) === 'ringing'
                  ? 'text-destructive dark:text-orange-300'
                  : ovenMode(order) === 'idle'
                    ? 'text-muted-foreground'
                    : 'text-foreground'
              "
            >
              <Icon name="lucide:alarm-clock" class="size-5" />
              <template v-if="ovenMode(order) === 'ringing'"
                >Tempo esgotado</template
              >
              <template v-else-if="ovenMode(order) === 'seen'">Visto</template>
              <template v-else-if="ovenMode(order) === 'running'">{{
                oven.remainingLabel(ovenKey(order))
              }}</template>
              <template v-else>Iniciar</template>
            </p>
          </component>
          <!-- Hover invertido: contraste garantido mesmo com o card em accent. -->
          <button
            type="button"
            class="group flex size-20 shrink-0 flex-col items-center justify-center gap-1 self-center rounded-xl border bg-background transition hover:border-primary hover:bg-primary hover:text-primary-foreground active:translate-y-px"
            :class="{
              'cursor-not-allowed opacity-50 hover:border-border hover:bg-background hover:text-foreground':
                !finishAvailable(order) || ovenFacts.isPending(order.pk),
            }"
            :disabled="!finishAvailable(order) || ovenFacts.isPending(order.pk)"
            :aria-busy="ovenFacts.isPending(order.pk)"
            :aria-label="`Confirmar conclusão da fornada de ${order.recipe_name}`"
            @click.stop="openOrder(order)"
          >
            <span class="text-xl font-semibold leading-none tabular-nums"
              >{{ cardAnchor(order) }} un.</span
            >
            <span
              class="text-xs font-semibold uppercase tracking-wide text-primary group-hover:text-primary-foreground"
              >{{
                ovenFacts.isPending(order.pk) ? "Abrindo…" : "Confirmar"
              }}</span
            >
          </button>
        </div>

        <!-- Fechadas: visíveis e esmaecidas, com a partição declarada. -->
        <div
          v-for="order in closedOrders"
          :key="order.pk"
          class="flex items-center justify-between gap-3 rounded-lg border bg-card p-4"
        >
          <div class="min-w-0 opacity-60">
            <p class="truncate text-base font-semibold">
              {{ order.recipe_name }}
            </p>
            <p class="truncate text-sm text-muted-foreground">
              {{ order.output_sku }}
            </p>
            <p
              v-if="order.correction_count"
              class="truncate text-xs text-muted-foreground"
            >
              {{ order.correction_count }}
              {{ order.correction_count === 1 ? "correção" : "correções" }}
              <template v-if="order.last_correction_at_display">
                · {{ order.last_correction_at_display }}
              </template>
            </p>
          </div>
          <div class="flex shrink-0 flex-col items-end gap-2">
            <p class="text-sm tabular-nums text-muted-foreground opacity-60">
              {{ order.full_price_qty || "0" }} OK
              <template v-if="order.discounted_qty">
                · {{ order.discounted_qty }} com desconto</template
              >
              <template v-if="order.loss_qty">
                · {{ order.loss_qty }} de perda</template
              >
            </p>
            <button
              v-if="correctionAvailable(order)"
              type="button"
              class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
              :aria-label="`Corrigir qualidade da fornada de ${order.recipe_name}`"
              @click="openCorrection(order)"
            >
              <Icon name="lucide:shield-check" class="size-3.5" />
              Corrigir qualidade
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Fornada avulsa: lista de receitas, nasce sem previsto. -->
    <UiSheet
      :open="recipePickerOpen"
      @update:open="(v: boolean) => (recipePickerOpen = v)"
    >
      <UiSheetContent side="bottom" title="Fornada avulsa">
        <template #content>
          <div class="grid grid-cols-2 gap-2 px-4 pb-6 sm:grid-cols-3">
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
          <UiDialogDescription>Toca neste aparelho.</UiDialogDescription>
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
          class="flex h-20 w-full items-center justify-center gap-3 rounded-lg border bg-background transition hover:bg-accent active:translate-y-px"
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
          class="grid h-20 place-items-center rounded-lg border text-center"
          :class="
            dialogMode === 'ringing'
              ? 'border-destructive/50 bg-destructive/10'
              : 'bg-background'
          "
        >
          <p
            v-if="dialogMode === 'ringing'"
            class="animate-pulse text-3xl font-bold text-destructive motion-reduce:animate-none dark:text-orange-300"
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
