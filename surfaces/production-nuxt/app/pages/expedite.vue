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

function openOrder(order: QCOrderCardProjection) {
  if (!order.can_close) return;
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
  const bits = [order.output_sku, order.position_ref, order.started_at_display].filter(Boolean);
  return bits.join(" · ");
});
const screenPlanned = computed(() => {
  if (!selectedOrder.value) return null;
  const value = Number(selectedOrder.value.planned_qty);
  return Number.isFinite(value) ? Math.round(value) : null;
});

// ── Timer do forno: lembrete armado por fornada, com som ────────────────────
// A ferramenta ATIVA do forneiro para conferir/retirar. Não confundir com o
// relógio de idade do lote (guardrail de esquecimento, que vive nos alertas).
const oven = useOvenTimers();
const ovenOrder = ref<QCOrderCardProjection | null>(null);
const ovenMinutes = ref("15");
const ovenKey = (order: QCOrderCardProjection) => String(order.pk);
function openOven(order: QCOrderCardProjection) {
  const key = ovenKey(order);
  if (oven.isRinging(key)) {
    oven.clear(key);
    return;
  }
  ovenOrder.value = order;
  ovenMinutes.value = String(oven.get(key)?.minutes ?? 15);
}
function bumpOven(delta: number) {
  const current = parseFloat(ovenMinutes.value.replace(",", ".")) || 0;
  ovenMinutes.value = String(Math.max(0, Math.round(current + delta)));
}
function confirmOven() {
  const order = ovenOrder.value;
  const minutes = parseFloat(ovenMinutes.value.replace(",", "."));
  if (!order || Number.isNaN(minutes) || minutes < 1) return;
  oven.arm(ovenKey(order), minutes);
  ovenOrder.value = null;
}
function cancelOven() {
  const order = ovenOrder.value;
  if (order) oven.clear(ovenKey(order));
  ovenOrder.value = null;
}
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <ProductionHeader
      v-model:query="query"
      title="Expedição"
      :count="kiosk?.closed_count"
      :count-label="`de ${kiosk?.total_count ?? 0} fechadas`"
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
             fornada é o botão quadrado do previsto, à direita. -->
        <div
          v-for="order in openOrders"
          :key="order.pk"
          role="button"
          tabindex="0"
          class="flex cursor-pointer items-stretch justify-between gap-3 rounded-lg border bg-card p-4 text-left transition hover:bg-accent"
          :class="{ 'border-primary ring-2 ring-primary/30': order.pk === nextPk }"
          :aria-label="`Timer do forno de ${order.recipe_name}`"
          @click="openOven(order)"
          @keydown.enter="openOven(order)"
        >
          <div class="min-w-0 flex-1">
            <p class="truncate text-base font-semibold">{{ order.recipe_name }}</p>
            <p class="truncate text-sm text-muted-foreground">
              {{ order.output_sku }}
              <template v-if="order.position_ref"> · {{ order.position_ref }}</template>
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
                oven.isRinging(ovenKey(order))
                  ? 'animate-pulse text-destructive dark:text-orange-300'
                  : oven.get(ovenKey(order))
                    ? 'text-foreground'
                    : 'text-muted-foreground'
              "
            >
              <Icon name="lucide:alarm-clock" class="size-5" />
              <template v-if="oven.isRinging(ovenKey(order))">Conferir o forno!</template>
              <template v-else-if="oven.get(ovenKey(order))">{{
                oven.remainingLabel(ovenKey(order))
              }}</template>
              <template v-else>Armar timer</template>
            </p>
          </div>
          <button
            type="button"
            class="grid size-20 shrink-0 place-items-center self-center rounded-xl border bg-background transition hover:border-primary hover:bg-accent"
            :aria-label="`Fechar a fornada de ${order.recipe_name}`"
            @click.stop="openOrder(order)"
          >
            <span class="text-2xl font-semibold leading-none tabular-nums">{{ order.planned_qty }}</span>
            <span class="mt-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">previsto</span>
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
            {{ order.full_price_qty || "0" }} a preço cheio
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
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Timer do forno · {{ ovenOrder?.output_sku }}</UiDialogTitle>
          <UiDialogDescription
            >Minutos até o lembrete de conferir/retirar. Toca neste
            aparelho.</UiDialogDescription
          >
        </UiDialogHeader>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Diminuir"
            @click="bumpOven(-1)"
          >
            −
          </button>
          <div class="relative w-full">
            <input
              v-model="ovenMinutes"
              type="text"
              inputmode="numeric"
              class="h-12 w-full rounded-md border bg-background text-center text-3xl font-bold tabular-nums outline-none focus:ring-1 focus:ring-ring"
              aria-label="Minutos do timer"
            />
            <span
              class="pointer-events-none absolute inset-y-0 right-3 grid place-items-center text-sm text-muted-foreground"
              >min</span
            >
          </div>
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Aumentar"
            @click="bumpOven(1)"
          >
            +
          </button>
        </div>
        <UiDialogFooter>
          <button
            v-if="ovenOrder && oven.get(ovenKey(ovenOrder))"
            type="button"
            class="mr-auto rounded-md border px-3 py-2 text-sm font-medium text-destructive transition hover:bg-destructive/10 dark:text-orange-300"
            @click="cancelOven()"
          >
            Cancelar timer
          </button>
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="ovenOrder = null"
          >
            Fechar
          </button>
          <button
            type="button"
            :disabled="!(parseFloat(ovenMinutes.replace(',', '.')) >= 1)"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="confirmOven()"
          >
            Iniciar timer
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
