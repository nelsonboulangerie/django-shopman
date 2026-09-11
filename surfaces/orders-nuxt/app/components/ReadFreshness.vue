<script setup lang="ts">
import type { ReadMetadata } from "~/types/readMetadata";
import { useNowTick } from "../composables/useNowTick";
import { realtimeIndicator } from "~/presentation/board";

const props = defineProps<{ metadata?: ReadMetadata | null; failed?: boolean; realtime?: "connecting" | "live" | "polling" }>();
const now = useNowTick(() => props.metadata?.generated_at ?? "");
const age = computed(() => Math.max(0, Math.floor((now.value - Date.parse(props.metadata?.generated_at ?? "")) / 1000)));
const clock = computed(() => props.metadata?.generated_at ? new Date(props.metadata.generated_at).toLocaleTimeString("pt-BR") : "");
</script>

<template>
  <p class="flex flex-wrap gap-x-3 gap-y-1 px-4 py-1 text-xs text-muted-foreground" data-read-freshness>
    <span v-if="metadata?.generated_at">Última leitura útil: <time :datetime="metadata.generated_at">{{ clock }}</time> · há {{ age }} s<span v-if="failed"> · atualização falhou</span></span>
    <span v-else>Horário da leitura indisponível</span>
    <span v-if="realtime">Conexão: {{ realtimeIndicator(realtime).label }}</span>
  </p>
</template>
