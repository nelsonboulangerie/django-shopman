<script setup lang="ts">
// Os filtros das Encomendas numa linha só: a `FilterBar` do operator-kit, no
// tamanho de toque do balcão (44 px). "Filtrar" abre Recebimento (Retiradas ·
// Entregas), Pagamento (A receber · Pagas, e "Na conta da casa" quando existe)
// e Via Pedido (Falta imprimir), cada opção com a contagem do que ela mostraria
// com os outros filtros como estão (`presentation/preorders`). O filtro ligado
// vira chip com X; sem chip, é "Todas". Combinam entre si.
//
// À direita da mesma linha mora o que age sobre o visível (o slot `actions`:
// o "Imprimir N vias" da tela).
//
// Pagamento a conferir não é opção escondida: é aviso próprio, com o gesto de
// ver só elas — "não sei" nunca some dentro de "a receber" ou de "pagas".
import {
  checkCount,
  checkPaymentNotice,
  filterDimensions,
  fromActiveFilters,
  toActiveFilters,
  type PreorderFilters,
} from "~/presentation/preorders";
import type { ActiveFilters } from "../../../operator-kit/app/types/filters";
import type { PreorderCard } from "~/types/preorders";

const props = defineProps<{ cards: readonly PreorderCard[] }>();
const filters = defineModel<PreorderFilters>({ required: true });

const dimensions = computed(() => filterDimensions(props.cards, filters.value));
const active = computed<ActiveFilters>({
  get: () => toActiveFilters(filters.value),
  set: (next) => { filters.value = fromActiveFilters(next); },
});
const notice = computed(() => checkPaymentNotice(checkCount(props.cards, filters.value)));

function toggleCheck() {
  filters.value = { ...filters.value, pay: filters.value.pay === "check" ? "all" : "check" };
}
</script>

<template>
  <div class="grid gap-2" data-preorders-filters>
    <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
      <FilterBar
        v-model="active"
        :dimensions="dimensions"
        label="Filtrar"
        touch
        class="min-w-0 flex-1"
        role="group"
        aria-label="Filtrar encomendas"
      />
      <slot name="actions" />
    </div>
    <div
      v-if="notice || filters.pay === 'check'"
      class="flex flex-wrap items-center gap-2 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning"
      data-preorders-check-notice
    >
      <Icon name="lucide:circle-help" class="size-4 shrink-0" />
      <span class="min-w-0 flex-1">{{ notice || "Mostrando só as encomendas com o pagamento a conferir." }}</span>
      <UiButton
        variant="outline"
        data-preorders-check-toggle
        @click="toggleCheck"
      >
        {{ filters.pay === "check" ? "Mostrar todas" : "Mostrar só essas" }}
      </UiButton>
    </div>
  </div>
</template>
