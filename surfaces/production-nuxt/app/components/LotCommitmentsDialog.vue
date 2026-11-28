<script setup lang="ts">
// As encomendas do produto na data, uma por linha, pela régua das reservas
// (WP-F10): "Clara · retirada · 9h · 1 un.". A linha aberta é estado da grade
// (`ProductionStageGrid`); aqui só se mostra. Primeiro nome e hora, nunca
// dinheiro nem telefone.
import { computed } from "vue";

import {
  orderedLabel,
  orderedUnits,
  promisedGap,
  promisedOrderLine,
  rowLabel,
  rowPromisedOrders,
} from "~/presentation/production";
import type { ProductionMatrixRowProjection } from "~/types/production";
import { dayLabel } from "../../../operator-kit/app/presentation/dates";

const props = defineProps<{
  row: ProductionMatrixRowProjection | null;
  /** O hoje da loja (ISO), para dizer "amanhã, sex 27/11". */
  today: string;
}>();

const emit = defineEmits<{
  close: [];
}>();

const orders = computed(() => (props.row ? rowPromisedOrders(props.row) : []));
const title = computed(() => {
  const row = props.row;
  if (!row) return "";
  return `${orderedLabel(orderedUnits(row.promised), row.output_unit)} · ${rowLabel(row)}`;
});
const description = computed(() => {
  const promised = props.row?.promised;
  return promised ? `Encomendas de ${dayLabel(promised.date, props.today).toLowerCase()}, pela hora.` : "";
});
const gap = computed(() => promisedGap(props.row?.promised, props.row?.output_unit));
</script>

<template>
  <!-- encomendas do produto na data -->
  <NuxtModal
    :open="row != null"
    :title="title"
    :description="description"
    @update:open="
      (v: boolean) => {
        if (!v) emit('close');
      }
    "
  >
    <template #body>
      <ul class="flex flex-col gap-2 text-sm" data-promised-orders>
        <li
          v-for="order in orders"
          :key="order.ref"
          class="flex items-center gap-2 rounded-md border p-2.5 tabular-nums"
          data-promised-order
        >
          <Icon
            name="lucide:shopping-bag"
            class="size-4 shrink-0 text-muted-foreground"
          />
          <span>{{ promisedOrderLine(order, row?.output_unit) }}</span>
        </li>
      </ul>
      <p
        v-if="gap"
        class="mt-3 text-sm font-medium text-highlighted"
        data-promised-gap
      >
        {{ gap }}
      </p>
    </template>
    <template #footer>
      <div class="flex w-full justify-end">
        <NuxtButton
          color="neutral"
          variant="outline"
          label="Fechar"
          @click="emit('close')"
        />
      </div>
    </template>
  </NuxtModal>
</template>
