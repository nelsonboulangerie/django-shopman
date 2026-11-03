<script setup lang="ts">
// As etapas da Bancada (modelo de navegação, 31/10/2026): Preparo, Produção e Finalização
// são o mesmo trabalho, e quem está na bancada passa de uma para outra o dia todo. Ficam
// no topo da tela, a um toque, em vez de três seções a dois toques pelo selo. Abas de
// sublinhado, para não se confundirem com as pílulas de dentro da tela (o "Por preparo ·
// Por insumo" da Preparação). Cada etapa continua com o próprio endereço.
import { BENCH_CUTS, type BenchCut } from "~/presentation/productionSections";

const props = defineProps<{ current: BenchCut }>();

const items = BENCH_CUTS.map((cut) => ({ label: cut.label, value: cut.key }));
const selected = computed({
  get: () => props.current,
  set: (key: string) => {
    const cut = BENCH_CUTS.find((item) => item.key === key);
    if (cut && cut.key !== props.current) void navigateTo(cut.to);
  },
});
</script>

<template>
  <div class="border-b border-default px-3 md:px-4 print:hidden" data-bench-cuts>
    <NuxtTabs
      v-model="selected"
      :items="items"
      :content="false"
      variant="link"
      class="w-full sm:w-auto"
      :ui="{ list: 'border-b-0', trigger: 'min-h-11 flex-1 sm:flex-none' }"
      aria-label="Etapas da bancada"
    />
  </div>
</template>
