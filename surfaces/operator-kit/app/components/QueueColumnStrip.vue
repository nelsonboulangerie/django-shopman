<script setup lang="ts">
// A coluna de fila RECOLHIDA (forma FILA do kit). No desktop e no tablet deitado ela
// é uma faixa de 56 px com o nome em pé; nas telas que empilham as colunas, uma barra
// baixa de largura inteira. A faixa inteira é o gancho: um toque devolve a coluna.
//
// A urgência sobrevive ao recolher: a contagem, o ponto no tom do estado (atrasado
// ou novo) e a frase curta ("1 atrasado"). Pedido novo faz a faixa pulsar até alguém
// olhar (`pulse`); o som é de quem o toca, não daqui. Regras puras e nome acessível
// em `presentation/queueColumns.ts`.
import { computed } from "vue";

import { queueStripLabel } from "../presentation/queueColumns";

const props = withDefaults(
  defineProps<{
    title: string;
    count: number;
    /** Quantos estão atrasados (0 = nenhum). */
    late?: number;
    /** Há novidade esperando alguém olhar: pulsa e mostra o ponto de "novo". */
    pulse?: boolean;
    icon?: string;
    /** Singular e plural do que a fila conta. */
    noun?: readonly [string, string];
    /**
     * A frase curta da urgência quando não é atraso ("aceita sozinho em 1:10", UX-KIT-V2,
     * prévia v4 `gestor-colunas4.html`). Atraso, quando há, fala primeiro.
     */
    summary?: string;
  }>(),
  { late: 0, pulse: false, icon: "", noun: () => ["pedido", "pedidos"] as const, summary: "" },
);

const emit = defineEmits<{ open: [] }>();

// Visual da suíte (`suite:`, só no app que pôs `data-suite="v3"`, UX-KIT-V2): a `.strip`
// da v4, 56 px, cantos de 12 px, contagem num círculo de 30 px, nome em pé de 16 px e a
// frase da urgência no tom dela; com novidade, o anel duplo na cor do app e o sino.

const label = computed(() => {
  const base = queueStripLabel(props.title, props.count, props.late, props.noun);
  return !props.late && props.summary ? `${base}, ${props.summary}` : base;
});
const lateText = computed(() => (props.late ? (props.late === 1 ? "1 atrasado" : `${props.late} atrasados`) : ""));
const tone = computed(() => (props.late ? "late" : props.pulse ? "new" : ""));
</script>

<template>
  <button
    type="button"
    class="relative flex min-h-action w-full items-center gap-2 overflow-hidden rounded-lg border bg-card px-2 text-left transition hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:h-full lg:min-h-80 lg:w-14 lg:flex-col lg:justify-start lg:px-0 lg:py-1 suite:rounded-xl suite:lg:gap-2.5 suite:lg:pt-1 suite:lg:pb-3"
    :class="pulse ? 'border-primary/60 suite:border-primary suite:shadow-[0_0_0_3px_color-mix(in_oklab,var(--primary)_22%,transparent),0_0_0_8px_color-mix(in_oklab,var(--primary)_9%,transparent)]' : 'suite:border-border'"
    :aria-label="label"
    :title="label"
    data-queue-strip
    :data-queue-strip-tone="tone || undefined"
    @click="emit('open')"
  >
    <span v-if="pulse" class="pointer-events-none absolute inset-0 bg-primary/10 motion-safe:animate-pulse suite:hidden" aria-hidden="true" data-queue-strip-pulse />
    <span class="relative grid size-action shrink-0 place-items-center text-muted-foreground suite:rounded-lg" :class="pulse ? 'suite:text-primary' : ''" aria-hidden="true">
      <Icon name="lucide:chevrons-right" class="size-5 suite:size-6" />
    </span>
    <span
      class="relative grid min-w-6 shrink-0 place-items-center rounded-full bg-muted px-1.5 text-xs font-bold tabular-nums suite:h-[30px] suite:min-w-[30px] suite:text-[15px]"
      :class="pulse ? 'suite:bg-primary suite:text-primary-foreground' : 'suite:bg-secondary'"
      aria-hidden="true"
      data-queue-strip-count
    >{{ count }}</span>
    <span
      v-if="tone || summary"
      class="relative size-2 shrink-0 rounded-full suite:size-2.5"
      :class="tone === 'late' ? 'bg-destructive' : tone === 'new' ? 'bg-primary suite:bg-warning' : 'bg-warning'"
      aria-hidden="true"
      data-queue-strip-dot
    />
    <span class="relative flex min-w-0 items-center gap-2 lg:[writing-mode:vertical-rl] lg:rotate-180 suite:lg:gap-2.5" aria-hidden="true">
      <Icon v-if="icon" :name="icon" class="size-4 shrink-0 text-muted-foreground lg:hidden" />
      <span class="text-sm font-bold uppercase tracking-wide suite:text-[16px] suite:font-semibold suite:normal-case suite:tracking-normal">{{ title }}</span>
      <span v-if="lateText" class="text-xs font-medium text-destructive dark:text-orange-300 suite:op-label suite:font-semibold" data-queue-strip-late>{{ lateText }}</span>
      <span v-else-if="summary" class="text-xs font-medium text-warning suite:op-label suite:font-semibold tnum" data-queue-strip-summary>{{ summary }}</span>
    </span>
    <span v-if="pulse" class="relative hidden flex-1 lg:block" aria-hidden="true" />
    <Icon v-if="pulse" name="lucide:bell-ring" class="relative hidden size-5 shrink-0 text-primary motion-safe:animate-pulse suite:lg:block" aria-hidden="true" />
  </button>
</template>
