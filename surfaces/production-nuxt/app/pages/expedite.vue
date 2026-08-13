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

const { kiosk, selectedDate, pending, submitting, refresh, finish, quickFinish } = useQcKiosk();

useHead({ title: "Expedição · Produção" });

const query = ref("");

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

function openOrder(order: QCOrderCardProjection) {
  if (!order.can_close) return;
  // Fechar com o alarme tocando: o lembrete cumpriu o papel — para o timer.
  if (oven.isRinging(ovenKey(order))) oven.clear(ovenKey(order));
  selectedOrder.value = order;
  selectedRecipe.value = null;
}

function openOffPlan(recipe: RecipeOptionProjection) {
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
const lastPayload = ref<{ quantity: string; partition: QcPartitionGroup[] } | null>(null);

async function onConfirm(payload: { quantity: string; partition: QcPartitionGroup[] }, force = false) {
  lastPayload.value = payload;
  const result = selectedOrder.value
    ? await finish(selectedOrder.value.pk, payload.quantity, payload.partition, force)
    : selectedRecipe.value
      ? await quickFinish(selectedRecipe.value.pk, payload.quantity, payload.partition, force)
      : { ok: false };
  if (result.ok) {
    useSonner.success("Fornada fechada.");
    backToBoard();
    return;
  }
  if (result.shortage) shortage.value = result.shortage;
}

function retryWithForce() {
  const payload = lastPayload.value;
  shortage.value = null;
  if (payload) onConfirm(payload, true);
}

const screenTitle = computed(
  () => selectedOrder.value?.recipe_name ?? selectedRecipe.value?.name ?? "",
);
const screenSubtitle = computed(() => {
  const order = selectedOrder.value;
  if (!order) return selectedRecipe.value ? "fornada avulsa" : "";
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

// ── Timer do forno: lembrete armado por fornada, com som ────────────────────
// A ferramenta ATIVA do forneiro para conferir/retirar — a ação de toda hora
// no rush: arma na enfornada, estende, pausa, e o Concluir emenda direto no
// fechamento. Não confundir com o relógio de idade do lote (alertas).
const oven = useOvenTimers();
const ovenOrder = ref<QCOrderCardProjection | null>(null);
const ovenMinutes = ref("15");
const ovenFresh = ref(true);
const ovenKey = (order: QCOrderCardProjection) => String(order.pk);

// Timers vivem no localStorage — o servidor não os conhece. O primeiro render
// do cliente precisa BATER com o SSR (idle) e só então ligar: senão a classe
// do alarme fica presa no HTML do servidor (mismatch de hidratação não é
// re-aplicado pelo Vue).
const hydrated = ref(false);
onMounted(() => {
  hydrated.value = true;
});

type OvenMode = "idle" | "running" | "paused" | "ringing";
function ovenMode(order: QCOrderCardProjection): OvenMode {
  if (!hydrated.value) return "idle";
  const key = ovenKey(order);
  if (oven.isRinging(key)) return "ringing";
  if (oven.isPaused(key)) return "paused";
  return oven.get(key) ? "running" : "idle";
}
const dialogMode = computed<OvenMode>(() =>
  ovenOrder.value ? ovenMode(ovenOrder.value) : "idle",
);

function openOven(order: QCOrderCardProjection) {
  ovenOrder.value = order;
  ovenMinutes.value = String(oven.get(ovenKey(order))?.minutes ?? 15);
  ovenFresh.value = true;
}
function ovenDigit(digit: string) {
  const next = ovenFresh.value ? digit : `${ovenMinutes.value}${digit}`;
  ovenMinutes.value = String(Math.min(999, Number(next) || 0));
  ovenFresh.value = false;
}
function ovenBackspace() {
  ovenMinutes.value = ovenMinutes.value.length <= 1 ? "0" : ovenMinutes.value.slice(0, -1);
}
function ovenAdd(minutes: number) {
  const order = ovenOrder.value;
  if (!order) return;
  if (dialogMode.value === "idle") {
    ovenMinutes.value = String((parseInt(ovenMinutes.value, 10) || 0) + minutes);
    ovenFresh.value = true;
    return;
  }
  // Correndo, pausado ou alarmando: soma ao vivo (alarmando = rearma).
  oven.extend(ovenKey(order), minutes);
}
function startOven() {
  const order = ovenOrder.value;
  const minutes = parseInt(ovenMinutes.value, 10);
  if (!order || !(minutes >= 1)) return;
  oven.arm(ovenKey(order), minutes);
  ovenOrder.value = null;
}
function pauseOven() {
  if (ovenOrder.value) oven.pause(ovenKey(ovenOrder.value));
}
function resumeOven() {
  if (ovenOrder.value) oven.resume(ovenKey(ovenOrder.value));
}
/** Concluir = a fornada saiu do forno: para o timer e emenda no fechamento. */
function concludeOven() {
  const order = ovenOrder.value;
  ovenOrder.value = null;
  if (!order) return;
  oven.clear(ovenKey(order));
  openOrder(order);
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
      :key="selectedOrder?.pk ?? `recipe-${selectedRecipe?.pk}`"
      :title="screenTitle"
      :subtitle="screenSubtitle"
      :planned="screenPlanned"
      :grades="kiosk.grades"
      :defects="kiosk.defects"
      :submitting="submitting"
      @back="backToBoard"
      @confirm="onConfirm($event)"
    />

    <!-- Painel de fornadas do dia. -->
    <div v-else class="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-4">
      <div class="flex items-center justify-between gap-3">
        <!-- Data: mesmo padrão de chips das outras telas do backstage. -->
        <div class="flex items-center gap-1 rounded-lg border bg-background p-0.5" role="group" aria-label="Data das fornadas">
          <button
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="!isCustomDate ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
            @click="selectedDate = ''"
          >
            Hoje
          </button>
          <button
            type="button"
            class="relative rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="isCustomDate ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
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

        <UiPopover :open="menuOpen" @update:open="(v: boolean) => (menuOpen = v)">
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
              @click="menuOpen = false; recipePickerOpen = true"
            >
              <Icon name="lucide:plus" class="size-4 text-muted-foreground" />
              Fornada avulsa
            </button>
          </UiPopoverContent>
        </UiPopover>
      </div>

      <p v-if="pending && !kiosk" class="py-10 text-center text-muted-foreground">Carregando…</p>
      <p v-else-if="kiosk && !kiosk.orders.length" class="py-10 text-center text-muted-foreground">
        Nenhuma fornada planejada para hoje.
      </p>

      <div class="grid gap-2">
        <!-- O toque no CARD abre o timer (a ação de toda hora); fechar a
             fornada é o botão quadrado do previsto, à direita. Alarmando, o
             card inteiro oscila em danger — visível do outro lado do fournil. -->
        <div
          v-for="order in openOrders"
          :key="order.pk"
          role="button"
          tabindex="0"
          class="flex cursor-pointer items-stretch justify-between gap-3 rounded-lg border bg-card p-4 text-left transition hover:bg-accent"
          :class="
            ovenMode(order) === 'ringing'
              ? 'qc-ringing border-destructive/60'
              : { 'border-primary ring-2 ring-primary/30': order.pk === nextPk }
          "
          :aria-label="`Timer do forno de ${order.recipe_name}`"
          @click="openOven(order)"
          @keydown.enter="openOven(order)"
        >
          <div class="min-w-0 flex-1">
            <p class="truncate text-base font-semibold">{{ order.recipe_name }}</p>
            <p class="truncate text-sm text-muted-foreground">
              {{ order.output_sku }}
              <template v-if="showPosition && order.position_ref"> · {{ order.position_ref }}</template>
              <template v-if="order.started_at_display"> · iniciada às {{ order.started_at_display }}</template>
              <template v-else> · ainda não iniciada</template>
              <template v-if="order.order_refs.length">
                · <span class="text-primary">{{ order.order_refs.length }}
                  {{ order.order_refs.length === 1 ? "pedido aguarda" : "pedidos aguardam" }}</span>
              </template>
            </p>
            <p
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
              <template v-if="ovenMode(order) === 'ringing'">Conferir Forno!</template>
              <template v-else-if="ovenMode(order) === 'paused'"
                >Pausado · {{ oven.remainingLabel(ovenKey(order)) }}</template
              >
              <template v-else-if="ovenMode(order) === 'running'">{{
                oven.remainingLabel(ovenKey(order))
              }}</template>
              <template v-else>Iniciar</template>
            </p>
          </div>
          <!-- Hover invertido: contraste garantido mesmo com o card em accent. -->
          <button
            type="button"
            class="group flex size-20 shrink-0 flex-col items-center justify-center self-center rounded-xl border bg-background pt-0.5 transition hover:border-primary hover:bg-primary hover:text-primary-foreground active:translate-y-px"
            :aria-label="`Finalizar a fornada de ${order.recipe_name}`"
            @click.stop="openOrder(order)"
          >
            <span class="text-xl font-semibold leading-none tabular-nums">{{ order.planned_qty }}</span>
            <span class="text-[9px] font-medium uppercase tracking-wide text-muted-foreground group-hover:text-primary-foreground/75">previstos</span>
            <span class="mt-1 text-[11px] font-semibold uppercase tracking-wide text-primary group-hover:text-primary-foreground">Finalizar</span>
          </button>
        </div>

        <!-- Fechadas: visíveis e esmaecidas, com a partição declarada. -->
        <div
          v-for="order in closedOrders"
          :key="order.pk"
          class="flex items-center justify-between gap-3 rounded-lg border bg-card p-4 opacity-50"
        >
          <div class="min-w-0">
            <p class="truncate text-base font-semibold">{{ order.recipe_name }}</p>
            <p class="truncate text-sm text-muted-foreground">{{ order.output_sku }}</p>
          </div>
          <p class="shrink-0 text-sm tabular-nums text-muted-foreground">
            {{ order.full_price_qty || "0" }} OK
            <template v-if="order.discounted_qty"> · {{ order.discounted_qty }} com desconto</template>
            <template v-if="order.loss_qty"> · {{ order.loss_qty }} de perda</template>
          </p>
        </div>
      </div>
    </div>

    <!-- Fornada avulsa: lista de receitas, nasce sem previsto. -->
    <UiSheet :open="recipePickerOpen" @update:open="(v: boolean) => (recipePickerOpen = v)">
      <UiSheetContent side="bottom" title="Fornada avulsa">
        <template #content>
          <div class="grid grid-cols-2 gap-2 px-4 pb-6 sm:grid-cols-3">
            <button
              v-for="recipe in kiosk?.recipes ?? []"
              :key="recipe.pk"
              type="button"
              class="rounded-md border bg-card px-3 py-2.5 text-left font-medium transition hover:bg-accent"
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
      @update:open="(v: boolean) => { if (!v) shortage = null; }"
      @confirm="retryWithForce"
    />

    <!-- timer do forno (lembrete por fornada, com som) -->
    <UiDialog
      :open="ovenOrder != null"
      @update:open="(v: boolean) => { if (!v) ovenOrder = null; }"
    >
      <UiDialogContent class="sm:max-w-sm" hide-close>
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
          <UiDialogTitle>Timer do forno · {{ ovenOrder?.recipe_name }}</UiDialogTitle>
          <UiDialogDescription>Toca neste aparelho.</UiDialogDescription>
        </UiDialogHeader>

        <!-- O mostrador: minutos a armar, restante ao vivo, ou o alarme. -->
        <div
          class="grid h-20 place-items-center rounded-lg border text-center"
          :class="dialogMode === 'ringing' ? 'border-destructive/50 bg-destructive/10' : 'bg-background'"
        >
          <p
            v-if="dialogMode === 'ringing'"
            class="animate-pulse text-2xl font-bold text-destructive dark:text-orange-300"
          >
            Conferir Forno!
          </p>
          <p v-else-if="dialogMode !== 'idle'" class="text-4xl font-bold tabular-nums">
            {{ ovenOrder ? oven.remainingLabel(ovenKey(ovenOrder)) : "" }}
            <span v-if="dialogMode === 'paused'" class="block text-xs font-medium uppercase tracking-wide text-muted-foreground">pausado</span>
          </p>
          <p v-else class="text-4xl font-bold tabular-nums">
            {{ ovenMinutes }}<span class="ml-1 text-base font-medium text-muted-foreground">min</span>
          </p>
        </div>

        <!-- Armando: numpad de 4 colunas — os +N moram ao lado de 3/6/9 (eles
             já substituem presets: 10 = C, +10) e o Iniciar fecha a grade. -->
        <div v-if="dialogMode === 'idle'" class="grid grid-cols-4 gap-1.5" role="group" aria-label="Minutos do timer">
          <template v-for="row in [[1, 2, 3], [4, 5, 6], [7, 8, 9]]" :key="row[0]">
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
            @click="ovenMinutes = '0'; ovenFresh = true"
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
            :disabled="!(parseInt(ovenMinutes, 10) >= 1)"
            class="rounded-md border border-transparent bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 active:translate-y-px disabled:opacity-50"
            @click="startOven()"
          >
            Iniciar
          </button>
        </div>

        <!-- Correndo/pausado/alarmando: +N ao vivo e o Concluir emenda no QC. -->
        <div v-else class="grid grid-cols-4 gap-1.5">
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
            type="button"
            class="rounded-md border border-transparent bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 active:translate-y-px"
            @click="concludeOven()"
          >
            Concluir
          </button>
        </div>

        <UiDialogFooter v-if="dialogMode === 'running' || dialogMode === 'paused'" class="gap-2">
          <button
            v-if="dialogMode === 'running'"
            type="button"
            class="mr-auto rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="pauseOven()"
          >
            Pausar
          </button>
          <button
            v-else
            type="button"
            class="mr-auto rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="resumeOven()"
          >
            Retomar
          </button>
        </UiDialogFooter>
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
</style>
