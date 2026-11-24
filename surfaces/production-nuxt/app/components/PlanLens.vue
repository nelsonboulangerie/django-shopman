<script setup lang="ts">
// Os conjuntos do Planejamento, abaixo das linhas que pedem decisão: o que não tem
// ressalva (um "sim" para todos, ou ver um a um) e o que não tem sugestão para o dia
// (planejar à mão). Os grupos e o envio moram na grade (`ProductionStageGrid`); aqui
// só se mostra e se avisa.
defineProps<{
  cleanCount: number;
  manualCount: number;
  cleanSummary: string;
  manualSummary: string;
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
  <!-- O que não tem ressalva vira conjunto: um "sim" para todos, ou ver um a um. -->
  <div
    v-if="cleanCount"
    class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-muted/40 px-4 py-3 last:border-b-0 lg:min-h-16"
    data-plan-clean
  >
    <span
      class="grid size-9 shrink-0 place-items-center rounded-full border border-border bg-card"
      aria-hidden="true"
    >
      <Icon name="lucide:list-checks" class="size-4 text-muted-foreground" />
    </span>
    <div class="min-w-0 flex-1 basis-60">
      <p class="op-body">
        <b class="font-semibold"
          >+{{ cleanCount }} produtos sem ressalva</b
        >
        <span class="text-muted-foreground">
          · insumos ok, sem encomenda, sem falta nem sobra repetida</span
        >
      </p>
      <p class="truncate op-micro text-muted-foreground">
        {{ cleanSummary }}
      </p>
    </div>
    <NuxtButton
      color="neutral"
      variant="outline"
      icon="i-lucide-list"
      label="Ver um a um"
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
          : `Planejar os ${cleanCount} como sugerido`
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
    <span
      class="grid size-9 shrink-0 place-items-center rounded-full border border-border bg-card"
      aria-hidden="true"
    >
      <Icon name="lucide:pencil-line" class="size-4 text-muted-foreground" />
    </span>
    <div class="min-w-0 flex-1 basis-60">
      <p class="op-body">
        <b class="font-semibold"
          >+{{ manualCount }} produtos sem sugestão para o dia</b
        >
        <span class="text-muted-foreground">
          · sem venda que sustente um número; planeje à mão se precisar</span
        >
      </p>
      <p class="truncate op-micro text-muted-foreground">
        {{ manualSummary }}
      </p>
    </div>
    <NuxtButton
      color="neutral"
      variant="outline"
      icon="i-lucide-list"
      label="Ver um a um"
      data-plan-manual-expand
      @click="emit('expand-manual')"
    />
  </div>
</template>
