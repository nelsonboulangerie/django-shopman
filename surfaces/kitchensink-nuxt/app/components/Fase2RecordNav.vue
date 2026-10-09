<script setup lang="ts">
// Protótipo do `OperatorRecordNav` (K5): anterior e próximo DENTRO da lista de onde a
// pessoa veio, com o recorte que ela aplicou ("3 de 18" é o 3º dos 18 que ela via).
// Teclas J e K, como nas listas com teclado. Sem lista de origem, o par não aparece.
import { computed } from "vue";
import { onKeyStroke } from "@vueuse/core";

const props = defineProps<{ index: number; total: number; noun: string }>();
const emit = defineEmits<{ go: [index: number] }>();

const hasPrev = computed(() => props.index > 0);
const hasNext = computed(() => props.index < props.total - 1);

function go(step: number) {
  const target = props.index + step;
  if (target < 0 || target >= props.total) return;
  emit("go", target);
}

function typing(event: KeyboardEvent) {
  const el = event.target as HTMLElement | null;
  return Boolean(el?.closest("input, textarea, [contenteditable=true]"));
}
onKeyStroke("j", (event) => {
  if (!typing(event)) go(1);
});
onKeyStroke("k", (event) => {
  if (!typing(event)) go(-1);
});
</script>

<template>
  <div class="flex items-center gap-2" data-fase2-record-nav>
    <NuxtFieldGroup>
      <NuxtButton
        icon="i-lucide-chevron-left"
        color="neutral"
        variant="outline"
        square
        :disabled="!hasPrev"
        :aria-label="`${noun} anterior`"
        @click="go(-1)"
      />
      <NuxtButton
        icon="i-lucide-chevron-right"
        color="neutral"
        variant="outline"
        square
        :disabled="!hasNext"
        :aria-label="`Próximo ${noun.toLowerCase()}`"
        @click="go(1)"
      />
    </NuxtFieldGroup>
    <span class="text-sm tabular-nums text-muted" aria-live="polite">{{ index + 1 }} de {{ total }}</span>
    <span class="hidden items-center gap-1 text-xs text-muted pointer-fine:inline-flex">
      <NuxtKbd value="K" /> <NuxtKbd value="J" />
    </span>
  </div>
</template>
