<script setup lang="ts">
// A coluna recolhida do painel (D, dono 13/11/2026, variante 5): guarda o lugar da
// coluna, na mesma ordem das abertas. Na linha do cabeçalho das abertas, só o número,
// no mesmo selo delas; um ponto no canto quando a coluna pede olho (vermelho para
// atraso, a cor principal para "precisa de você"). Abaixo, o nome em pé; no pé, o
// abrir. A frase inteira (quantos, atrasados, próximo pronto) vai no título e no nome
// acessível. A tira inteira é o botão que abre. Regras: `presentation/boardStrip.ts`.
import type { BoardStrip } from "~/presentation/boardStrip";

defineProps<{ strip: BoardStrip; shortcut: string }>();
const emit = defineEmits<{ open: [] }>();
</script>

<template>
  <!-- O mesmo fundo das colunas abertas (a tira é a coluna, fechada); o botão é ela
       inteira, sem fundo próprio. O foco é desenhado para dentro: a tira encosta na
       borda do painel do Splitter, que recorta o que passa dela. -->
  <div class="h-full w-11 shrink-0 rounded-xl bg-elevated/60">
  <NuxtButton
    color="neutral"
    variant="ghost"
    class="relative h-full w-full flex-col items-center justify-start gap-0 p-0 pb-3 focus-visible:-outline-offset-2"
    :aria-label="`${strip.label} (atalho: ${shortcut})`"
    :title="strip.label"
    :data-board-strip="strip.key"
    @click="emit('open')"
  >
    <span class="grid h-11 w-full place-items-center">
      <span
        class="rounded-full bg-default px-2 op-micro font-semibold tnum text-highlighted"
        data-board-count
        >{{ strip.count }}</span
      >
    </span>
    <span
      v-if="strip.dot"
      class="absolute end-1.5 top-1.5 size-2 rounded-full"
      :class="strip.dot === 'late' ? 'bg-error' : 'bg-primary'"
      :data-board-strip-dot="strip.dot"
    />
    <span
      class="mt-3 rotate-180 whitespace-nowrap font-semibold [writing-mode:vertical-rl]"
    >
      {{ strip.title }}
    </span>
    <Icon name="i-lucide-chevrons-right" class="mt-auto size-4" />
  </NuxtButton>
  </div>
</template>
