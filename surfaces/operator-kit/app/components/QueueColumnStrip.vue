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
  }>(),
  { late: 0, pulse: false, icon: "", noun: () => ["pedido", "pedidos"] as const },
);

const emit = defineEmits<{ open: [] }>();

const label = computed(() => queueStripLabel(props.title, props.count, props.late, props.noun));
const lateText = computed(() => (props.late ? (props.late === 1 ? "1 atrasado" : `${props.late} atrasados`) : ""));
const tone = computed(() => (props.late ? "late" : props.pulse ? "new" : ""));
</script>

<template>
  <button
    type="button"
    class="relative flex min-h-action w-full items-center gap-2 overflow-hidden rounded-lg border bg-card px-2 text-left transition hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:h-full lg:min-h-80 lg:w-14 lg:flex-col lg:justify-start lg:px-0 lg:py-1"
    :class="pulse ? 'border-primary/60' : ''"
    :aria-label="label"
    :title="label"
    data-queue-strip
    :data-queue-strip-tone="tone || undefined"
    @click="emit('open')"
  >
    <span v-if="pulse" class="pointer-events-none absolute inset-0 bg-primary/10 motion-safe:animate-pulse" aria-hidden="true" data-queue-strip-pulse />
    <span class="relative grid size-action shrink-0 place-items-center text-muted-foreground" aria-hidden="true">
      <Icon name="lucide:chevrons-right" class="size-5" />
    </span>
    <span class="relative grid min-w-6 shrink-0 place-items-center rounded-full bg-muted px-1.5 text-xs font-bold tabular-nums" aria-hidden="true" data-queue-strip-count>{{ count }}</span>
    <span
      v-if="tone"
      class="relative size-2 shrink-0 rounded-full"
      :class="tone === 'late' ? 'bg-destructive' : 'bg-primary'"
      aria-hidden="true"
      data-queue-strip-dot
    />
    <span class="relative flex min-w-0 items-center gap-2 lg:[writing-mode:vertical-rl] lg:rotate-180" aria-hidden="true">
      <Icon v-if="icon" :name="icon" class="size-4 shrink-0 text-muted-foreground lg:hidden" />
      <span class="text-sm font-bold uppercase tracking-wide">{{ title }}</span>
      <span v-if="lateText" class="text-xs font-medium text-destructive dark:text-orange-300" data-queue-strip-late>{{ lateText }}</span>
    </span>
  </button>
</template>
