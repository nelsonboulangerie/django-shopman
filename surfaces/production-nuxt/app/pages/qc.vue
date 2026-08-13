<script setup lang="ts">
// Quiosque de QC do fournil (ADR-017 §9 / QC-FORNADA §5). Duas telas:
//   1. painel de ORDENS do dia (não catálogo de SKU): a ordem já traz forno,
//      horário e previsto, e é o previsto que faz a fornada normal fechar em
//      poucos toques. Sem busca: são 5–15 fornadas/dia.
//   2. tela de fechamento (QcCloseScreen), numpad ancorado.
// Kiosk de operador em tela cheia (registrado no app.vue), atrás do gate.
import type { QCOrderCardProjection, RecipeOptionProjection, ProductionShortageError } from "~/types/production";
import type { QcPartitionGroup } from "~/presentation/qc";

const { kiosk, pending, submitting, finish, quickFinish } = useQcKiosk();

useHead({ title: "QC da fornada" });

// ── Navegação interna (painel ⇄ fechamento) ─────────────────────────────────
const selectedOrder = ref<QCOrderCardProjection | null>(null);
const selectedRecipe = ref<RecipeOptionProjection | null>(null);
const recipePickerOpen = ref(false);

const openOrders = computed(() => (kiosk.value?.orders ?? []).filter((o) => !o.closed));
const closedOrders = computed(() => (kiosk.value?.orders ?? []).filter((o) => o.closed));
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

// ── Fechamento (com retry de force no shortage, como no KDS) ────────────────
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
  if (!order) return selectedRecipe.value ? "fornada fora do plano" : "";
  const bits = [order.output_sku, order.position_ref, order.started_at_display].filter(Boolean);
  return bits.join(" · ");
});
const screenPlanned = computed(() => {
  if (!selectedOrder.value) return null;
  const value = Number(selectedOrder.value.planned_qty);
  return Number.isFinite(value) ? Math.round(value) : null;
});
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <!-- Tela 2: fechamento. -->
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

    <!-- Tela 1: painel de fornadas do dia. -->
    <div v-else class="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-4">
      <header class="flex items-center justify-between gap-3">
        <div>
          <h1 class="text-lg font-semibold">Fechamento de fornada</h1>
          <p class="text-sm text-muted-foreground">{{ kiosk?.selected_date_display }}</p>
        </div>
        <div class="flex items-center gap-3">
          <span class="rounded-md border bg-muted/40 px-3 py-2 text-sm tabular-nums">
            {{ kiosk?.closed_count ?? 0 }} de {{ kiosk?.total_count ?? 0 }} fechadas
          </span>
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm text-muted-foreground transition hover:bg-accent"
            @click="recipePickerOpen = true"
          >
            fornada fora do plano
          </button>
        </div>
      </header>

      <p v-if="pending && !kiosk" class="py-10 text-center text-muted-foreground">Carregando…</p>
      <p v-else-if="kiosk && !kiosk.orders.length" class="py-10 text-center text-muted-foreground">
        Nenhuma fornada planejada para hoje.
      </p>

      <div class="grid gap-2">
        <button
          v-for="order in openOrders"
          :key="order.pk"
          type="button"
          class="flex items-center justify-between gap-3 rounded-lg border bg-card p-4 text-left transition hover:bg-accent"
          :class="{ 'border-primary ring-2 ring-primary/30': order.pk === nextPk }"
          @click="openOrder(order)"
        >
          <div class="min-w-0">
            <p class="truncate text-base font-semibold">{{ order.recipe_name }}</p>
            <p class="truncate text-sm text-muted-foreground">
              {{ order.output_sku }}
              <template v-if="order.position_ref"> · {{ order.position_ref }}</template>
              <template v-if="order.started_at_display"> · no forno desde {{ order.started_at_display }}</template>
              <template v-else> · ainda não iniciada</template>
            </p>
          </div>
          <div class="shrink-0 text-right">
            <p class="text-2xl font-semibold tabular-nums">{{ order.planned_qty }}</p>
            <p class="text-xs uppercase tracking-wide text-muted-foreground">previsto</p>
          </div>
        </button>

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

    <!-- Fornada fora do plano: lista de receitas, nasce sem previsto. -->
    <UiSheet :open="recipePickerOpen" @update:open="(v: boolean) => (recipePickerOpen = v)">
      <UiSheetContent side="bottom" title="Fornada fora do plano">
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
  </div>
</template>
