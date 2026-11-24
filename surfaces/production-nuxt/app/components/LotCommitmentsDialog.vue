<script setup lang="ts">
// As encomendas que dependem da produção de um produto, uma por linha. A linha
// aberta é estado da grade (`ProductionStageGrid`); aqui só se mostra.
import { computed } from "vue";

import {
  rowCommitments,
  rowCommittedUnits,
  rowLabel,
} from "~/presentation/production";
import type { ProductionMatrixRowProjection } from "~/types/production";

const props = defineProps<{
  row: ProductionMatrixRowProjection | null;
}>();

const emit = defineEmits<{
  close: [];
}>();

const commitmentsList = computed(() =>
  props.row ? rowCommitments(props.row) : [],
);
</script>

<template>
  <!-- pedidos vinculados -->
  <NuxtModal
    :open="row != null"
    :title="`${row ? rowCommittedUnits(row) : 0} un. comprometidas · ${row ? rowLabel(row) : ''}`"
    :description="`${row?.output_sku ?? ''} · encomendas confirmadas que dependem desta produção.`"
    @update:open="
      (v: boolean) => {
        if (!v) emit('close');
      }
    "
  >
    <template #body>
      <ul class="flex flex-col gap-2 text-sm">
        <li
          v-for="commitment in commitmentsList"
          :key="commitment.ref"
          class="flex items-center justify-between gap-3 rounded-md border p-2.5"
        >
          <span class="inline-flex items-center gap-2">
            <Icon
              name="lucide:shopping-bag"
              class="size-4 text-muted-foreground"
            />
            <span class="font-medium">{{ commitment.ref }}</span>
            <NuxtBadge color="neutral" :label="commitment.status_label" />
          </span>
          <span class="tabular-nums text-muted-foreground"
            >{{ commitment.qty_required }} un.</span
          >
        </li>
      </ul>
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
