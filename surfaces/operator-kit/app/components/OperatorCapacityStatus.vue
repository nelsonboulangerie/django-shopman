<script setup lang="ts">
// Capacidade do serviço, de relance, no cluster de status do rail.
//
// Pergunta do dono (17/09): "como sabemos se os apps de chão de loja vão
// engasgar no pico?". O processo Nitro lê a memória e a CPU do CONTÊINER
// (/health/capacity) e o Admin decide os limites: abaixo da atenção o ponto fica
// neutro, acima fica âmbar, acima do crítico vermelho. O detalhe diz os números
// em português e há quanto tempo foram lidos — o estado nunca depende só da cor.
//
// Mesma gramática do gatilho de saúde do terminal do PDV (`RailItem`: tokens
// `rail-foreground`, altura, rótulo no estado estendido). O popover é o primitivo
// do reka-ui — o mesmo que o `UiPopover` dos apps embrulha — porque a layer é
// montada também em apps sem o `UiPopover` (Central, B.I., Compras).
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";
import { useNow } from "@vueuse/core";
import {
  CAPACITY_LEVEL_META,
  capacityAriaLabel,
  capacityGuidance,
  capacityLevel,
  capacitySummary,
  capacityThresholdsText,
  capacityUpdatedAgo,
} from "../presentation/capacity";

const { reading, authorized, stale } = useOperatorCapacity();
const { showLabels } = useRailState();
const now = useNow({ interval: 10_000 });

const level = computed(() => capacityLevel(reading.value));
const meta = computed(() => CAPACITY_LEVEL_META[level.value]);
const summary = computed(() => capacitySummary(reading.value));
const ariaLabel = computed(() => capacityAriaLabel(reading.value, level.value));
const updated = computed(() => capacityUpdatedAgo(reading.value?.measured_at, now.value.getTime()));
const guidance = computed(() => capacityGuidance(level.value, reading.value?.thresholds ?? null));
const thresholdsText = computed(() => capacityThresholdsText(reading.value?.thresholds ?? null));
</script>

<template>
  <PopoverRoot v-if="authorized && reading">
    <PopoverTrigger as-child>
      <button
        type="button"
        data-capacity-trigger
        :data-capacity-level="level"
        class="flex h-11 items-center rounded-md text-rail-foreground/80 transition hover:bg-rail-foreground/10 hover:text-rail-foreground"
        :class="showLabels ? 'w-full gap-3 px-2.5' : 'w-11 justify-center'"
        :aria-label="ariaLabel"
        :title="showLabels ? undefined : ariaLabel"
      >
        <span class="relative grid size-5 shrink-0 place-items-center">
          <Icon name="lucide:gauge" class="size-5" />
          <span
            data-capacity-dot
            class="absolute -bottom-0.5 -right-1 size-2 rounded-full ring-2 ring-rail"
            :class="meta.dot"
          />
        </span>
        <span v-if="showLabels" class="min-w-0 truncate text-sm">Capacidade · {{ meta.label }}</span>
      </button>
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent
        side="right"
        align="end"
        :side-offset="8"
        :collision-padding="8"
        data-capacity-detail
        class="z-50 w-72 rounded-md border bg-popover p-3 text-popover-foreground shadow-md outline-hidden"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm font-semibold">Capacidade do serviço</span>
          <span class="text-xs font-semibold" :class="meta.text">{{ meta.label }}</span>
        </div>
        <p class="mt-2 text-sm font-medium tabular-nums" data-capacity-summary>{{ summary }}</p>
        <p v-if="updated" class="text-xs text-muted-foreground" data-capacity-updated>
          {{ updated }}<template v-if="stale"> · sem resposta na última tentativa</template>
        </p>
        <p v-if="level !== 'unknown'" class="mt-2 text-xs text-muted-foreground">{{ guidance }}</p>
        <p v-if="thresholdsText && level !== 'unknown'" class="mt-1 text-xs text-muted-foreground">
          {{ thresholdsText }}
        </p>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
