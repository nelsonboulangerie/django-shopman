<script setup lang="ts">
import type { ReadMetadata } from "~/types/readMetadata";
import { useNowTick } from "../composables/useNowTick";
import { realtimeIndicator } from "~/presentation/board";

// `inline` (UX-KIT-V1): a mesma frase, sem a faixa própria, para morar no fim da linha de
// recortes do cabeçalho de uma linha. O texto não encolhe: "Última leitura útil" segue
// escrito, porque é o que prova ao operador que a fila não parou.
const props = defineProps<{ metadata?: ReadMetadata | null; failed?: boolean; realtime?: "connecting" | "live" | "polling"; inline?: boolean }>();
const now = useNowTick(() => props.metadata?.generated_at ?? "");
const age = computed(() => Math.max(0, Math.floor((now.value - Date.parse(props.metadata?.generated_at ?? "")) / 1000)));
const clock = computed(() => props.metadata?.generated_at ? new Date(props.metadata.generated_at).toLocaleTimeString("pt-BR") : "");
</script>

<template>
  <component
    :is="inline ? 'span' : 'p'"
    class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground"
    :class="inline ? 'whitespace-nowrap' : 'px-4 py-1'"
    data-read-freshness
  >
    <span v-if="metadata?.generated_at">Última leitura útil: <time :datetime="metadata.generated_at">{{ clock }}</time> · há {{ age }} s<span v-if="failed"> · atualização falhou</span></span>
    <span v-else>Horário da leitura indisponível</span>
    <span v-if="realtime">Conexão: {{ realtimeIndicator(realtime).label }}</span>
  </component>
</template>
