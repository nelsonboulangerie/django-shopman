<script setup lang="ts">
// Os conjuntos do Planejamento, abaixo das linhas que pedem decisão: o que está no
// padrão (um "sim" para todos, ou ver um a um) e o que não tem sugestão para o dia
// (planejar à mão). KISS (dono, 28/11): o conjunto é o número e o gesto, sem a frase
// que explica o critério nem a lista de nomes. Os grupos e o envio moram na grade (`ProductionStageGrid`); aqui
// só se mostra e se avisa.
defineProps<{
  cleanCount: number;
  manualCount: number;
  canPlanCleanSet: boolean;
  bulkSubmitting: boolean;
  inlineBusy: boolean;
}>();

const emit = defineEmits<{
  "expand-clean": [];
  "expand-manual": [];
  "plan-clean": [];
}>();
</script>

<template>
  <!-- O que está no padrão vira conjunto: um "sim" para todos, ou ver um a um. -->
  <div
    v-if="cleanCount"
    class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-muted/40 px-4 py-3 last:border-b-0 lg:min-h-16"
    data-plan-clean
  >
    <div class="min-w-0 flex-1 basis-60">
      <p class="op-body">
        <b class="font-semibold">{{ cleanCount }} no padrão</b>
      </p>
    </div>
    <NuxtButton
      color="neutral"
      variant="outline"
      icon="i-lucide-list"
      label="Ver"
      data-plan-clean-expand
      @click="emit('expand-clean')"
    />
    <NuxtButton
      color="primary"
      variant="outline"
      icon="i-lucide-check-check"
      :disabled="
        !canPlanCleanSet || bulkSubmitting || inlineBusy
      "
      :aria-busy="bulkSubmitting"
      :label="
        bulkSubmitting
          ? 'Planejando…'
          : `Planejar os ${cleanCount}`
      "
      data-plan-clean-all
      @click="emit('plan-clean')"
    />
  </div>

  <!-- Sem sugestão para o dia (bases, recheios, o que não vende hoje): conjunto
       que se abre para planejar à mão. -->
  <div
    v-if="manualCount"
    class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-muted/25 px-4 py-3 last:border-b-0 lg:min-h-16"
    data-plan-manual
  >
    <div class="min-w-0 flex-1 basis-60">
      <p class="op-body">
        <b class="font-semibold">{{ manualCount }} sem sugestão</b>
      </p>
    </div>
    <NuxtButton
      color="neutral"
      variant="outline"
      icon="i-lucide-list"
      label="Ver"
      data-plan-manual-expand
      @click="emit('expand-manual')"
    />
  </div>
</template>
