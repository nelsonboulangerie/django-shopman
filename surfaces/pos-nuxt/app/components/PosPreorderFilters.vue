<script setup lang="ts">
// Os filtros das Encomendas, em chips combináveis com a contagem de cada um:
// Recebimento (Todas · Retiradas · Entregas), Pagamento (Todas · A receber ·
// Pagas, e "Na conta da casa" quando existe) e Via Pedido (Todas · Falta
// imprimir). Um toque troca a lista; a contagem de cada chip é a do que ele
// mostraria com os outros filtros como estão (`presentation/preorders`).
//
// Pagamento a conferir não é chip escondido: é aviso próprio, com o gesto de
// ver só elas — "não sei" nunca some dentro de "a receber" ou de "pagas".
import {
  checkCount,
  checkPaymentNotice,
  filterChips,
  type PreorderFilters,
} from "~/presentation/preorders";
import type { PreorderCard } from "~/types/preorders";

const props = defineProps<{ cards: readonly PreorderCard[] }>();
const filters = defineModel<PreorderFilters>({ required: true });

const chips = computed(() => filterChips(props.cards, filters.value));
const notice = computed(() => checkPaymentNotice(checkCount(props.cards, filters.value)));

const GROUPS = [
  { key: "fulfillment", label: "Recebimento" },
  { key: "pay", label: "Pagamento" },
  { key: "print", label: "Via Pedido" },
] as const;

function choose(group: keyof PreorderFilters, value: string) {
  filters.value = { ...filters.value, [group]: value };
}
</script>

<template>
  <div class="grid gap-3" data-preorders-filters>
    <div class="flex items-center gap-2 text-sm font-semibold">
      <Icon name="lucide:list-filter" class="size-4 text-muted-foreground" aria-hidden="true" />
      Mostrar
    </div>
    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <div
        v-for="group in GROUPS"
        :key="group.key"
        class="grid content-start gap-1.5"
        role="group"
        :aria-label="`Filtrar por ${group.label}`"
        :data-preorders-filter="group.key"
      >
        <span class="text-xs font-medium text-muted-foreground">{{ group.label }}</span>
        <div class="flex flex-wrap gap-1.5">
          <UiFilterChip
            v-for="chip in chips[group.key]"
            :key="chip.key"
            :active="filters[group.key] === chip.key"
            :count="chip.count"
            :aria-pressed="filters[group.key] === chip.key"
            :aria-label="`${group.label}, ${chip.label}: ${chip.count}`"
            :data-preorders-filter-chip="`${group.key}:${chip.key}`"
            @click="choose(group.key, chip.key)"
          >
            {{ chip.label }}
          </UiFilterChip>
        </div>
      </div>
    </div>
    <div
      v-if="notice || filters.pay === 'check'"
      class="flex flex-wrap items-start gap-2 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning"
      data-preorders-check-notice
    >
      <Icon name="lucide:circle-help" class="mt-0.5 size-4 shrink-0" />
      <span class="min-w-0 flex-1">{{ notice || "Mostrando só as encomendas com o pagamento a conferir." }}</span>
      <UiButton
        variant="outline"
        size="sm"
        data-preorders-check-toggle
        @click="choose('pay', filters.pay === 'check' ? 'all' : 'check')"
      >
        {{ filters.pay === "check" ? "Mostrar todas" : "Mostrar só essas" }}
      </UiButton>
    </div>
  </div>
</template>
