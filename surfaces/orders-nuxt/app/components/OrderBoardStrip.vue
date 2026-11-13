<script setup lang="ts">
// A coluna recolhida do quadro (D, dono 13/11/2026): guarda o lugar da coluna, na
// mesma ordem das abertas, e diz sem abrir se ela pede olho. De cima para baixo, na
// altura do cabeçalho das colunas abertas: o abrir; o número no mesmo selo das
// abertas; os sinais (ícone e número, um por bloco); o nome em pé. A tira inteira é
// o botão que abre. As regras dos sinais são de `presentation/boardStrip.ts`.
import type { BoardStrip, StripSignalKind } from "~/presentation/boardStrip";

defineProps<{ strip: BoardStrip; shortcut: string }>();
const emit = defineEmits<{ open: [] }>();

const TONE: Record<StripSignalKind, string> = {
  need: "bg-primary text-inverted",
  late: "bg-error/10 text-error",
  next: "bg-default text-highlighted ring ring-default",
};
</script>

<template>
  <NuxtButton
    color="neutral"
    variant="soft"
    class="h-full w-12 shrink-0 flex-col items-center justify-start gap-0 p-0 pb-3"
    :aria-label="`${strip.label} (atalho: ${shortcut})`"
    :title="strip.label"
    :data-board-strip="strip.key"
    @click="emit('open')"
  >
    <span class="grid h-12 w-full place-items-center border-b border-default">
      <Icon name="i-lucide-panel-left-open" class="size-4" />
    </span>
    <OperatorCountChip :count="strip.count" class="mt-2" />
    <span
      v-if="strip.signals.length"
      class="mt-2 flex flex-col items-center gap-1"
      data-board-strip-signals
    >
      <span
        v-for="signal in strip.signals"
        :key="signal.kind"
        class="flex h-6 w-10 items-center justify-center gap-0.5 rounded-md op-micro font-semibold"
        :class="TONE[signal.kind]"
        :title="signal.label"
        :data-board-strip-signal="signal.kind"
      >
        <Icon :name="signal.icon" class="size-3.5" />{{ signal.short }}
      </span>
    </span>
    <span
      class="mt-3 rotate-180 whitespace-nowrap font-semibold [writing-mode:vertical-rl]"
    >
      {{ strip.title }}
    </span>
  </NuxtButton>
</template>
