<script setup lang="ts">
// Os filtros de dinheiro das Encomendas: Todas · A receber · Pagas, com a
// contagem em cada um (e "Na conta da casa" quando existe). Um toque troca a
// lista. Pagamento a conferir não é filtro escondido num chip: é aviso próprio,
// com o gesto de ver só elas — "não sei" nunca some dentro de "a receber" ou de
// "pagas" (ver `presentation/preorders`).
import { checkPaymentNotice, paymentFilterChips, type PaymentCounts, type PaymentFilter } from "~/presentation/preorders";

const props = defineProps<{ counts: PaymentCounts }>();
const filter = defineModel<PaymentFilter>({ required: true });

const chips = computed(() => paymentFilterChips(props.counts));
const notice = computed(() => checkPaymentNotice(props.counts.check));
</script>

<template>
  <div class="grid gap-2">
    <div class="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filtrar pelo pagamento" data-preorders-filter>
      <UiFilterChip
        v-for="chip in chips"
        :key="chip.key"
        :active="filter === chip.key"
        :count="chip.count"
        :aria-pressed="filter === chip.key"
        :aria-label="`${chip.label}: ${chip.count}`"
        :data-preorders-filter-chip="chip.key"
        @click="filter = chip.key"
      >
        {{ chip.label }}
      </UiFilterChip>
    </div>
    <div
      v-if="notice"
      class="flex flex-wrap items-start gap-2 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning"
      data-preorders-check-notice
    >
      <Icon name="lucide:circle-help" class="mt-0.5 size-4 shrink-0" />
      <span class="min-w-0 flex-1">{{ notice }}</span>
      <UiButton
        variant="outline"
        size="sm"
        data-preorders-check-toggle
        @click="filter = filter === 'check' ? 'all' : 'check'"
      >
        {{ filter === "check" ? "Mostrar todas" : "Mostrar só essas" }}
      </UiButton>
    </div>
  </div>
</template>
