<script setup lang="ts">
// Protótipo do `OperatorQuickFilters` (K4): o filtro rápido É a navegação secundária
// (dono, 09/10). Abas com contagem na toolbar esquerda; os favoritos fixados entram no
// fim, com a estrela. Até 4 opções rolam no celular sem cortar rótulo; com mais, a
// peça vira `NuxtSelect` (regra da toolbar do kit).
import type { QuickFilter } from "../types/fase2";
import { computed } from "vue";


const props = withDefaults(defineProps<{ items: readonly QuickFilter[]; label: string; selectAbove?: number }>(), {
  selectAbove: 4,
});
const model = defineModel<string>({ required: true });

const tabs = computed(() =>
  props.items.map((item) => ({
    label: item.label,
    value: item.value,
    icon: item.favorite ? "i-lucide-star" : undefined,
    badge: item.count === undefined ? undefined : { label: String(item.count), color: "neutral" as const },
  })),
);
const options = computed(() =>
  props.items.map((item) => ({
    label: item.count === undefined ? item.label : `${item.label} (${item.count})`,
    value: item.value,
  })),
);
const asSelect = computed(() => props.items.length > props.selectAbove);
</script>

<template>
  <div class="min-w-0" data-fase2-quick-filters>
    <NuxtSelect
      v-if="asSelect"
      v-model="model"
      :items="options"
      :aria-label="label"
      class="w-full sm:hidden"
    />
    <div class="overflow-x-auto" :class="asSelect ? 'max-sm:hidden' : ''">
      <NuxtTabs v-model="model" :items="tabs" :content="false" variant="pill" :aria-label="label" class="w-max" />
    </div>
  </div>
</template>
