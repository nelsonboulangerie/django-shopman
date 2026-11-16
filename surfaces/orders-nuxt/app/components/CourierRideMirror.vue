<script setup lang="ts">
// O ESPELHO da corrida: uma linha que diz o momento dela e, quando o gesto é de
// quem está no balcão, o botão pronto. Mora na parte "Corridas" da página Entregas
// (e, no próximo passo, no Painel). Tocar na linha abre o detalhe da corrida
// (`/deliveries?ride=<chave da corrida>`).
import type { DeliveryRideProjection } from "~/generated/ordersContract";
import { rideColor } from "~/presentation/ridePalette";
import { beforeHandoff, bagsWord, rideLine } from "~/presentation/deliveries";

const props = defineProps<{ ride: DeliveryRideProjection; now: number; busy?: boolean }>();
const emit = defineEmits<{ back: [] }>();
const tone = computed(() => rideColor(props.ride.number - 1));
const line = computed(() => rideLine(props.ride, props.now));
const showBags = computed(() => beforeHandoff(props.ride));
</script>

<template>
  <NuxtLink
    :to="{ path: '/deliveries', query: { ride: ride.key } }"
    class="group flex items-center gap-3 rounded-xl border border-default bg-default py-2.5 pr-2.5 pl-3 shadow-xs transition hover:border-accented hover:shadow-sm focus-visible:outline-2 focus-visible:outline-primary"
    :style="{ borderLeft: `6px solid ${tone.bg}` }"
    data-ride-mirror
  >
    <span class="grid size-8 shrink-0 place-items-center rounded-lg op-label font-bold" :style="{ background: tone.bg, color: tone.fg }">{{ ride.letter }}</span>
    <span class="min-w-0 flex-1">
      <span class="flex items-center gap-1.5 op-body font-semibold text-highlighted">
        <NuxtIcon :name="line.icon" class="size-4 shrink-0 text-muted" :class="ride.state === 'searching' || ride.state === 'reopened' ? 'animate-pulse' : ''" />
        <span class="truncate">{{ line.title }}</span>
      </span>
      <span class="flex flex-wrap items-center gap-x-1.5 op-micro text-muted">
        <span v-for="stop in ride.stops" :key="stop.ref" class="tabular-nums" :class="stop.done ? 'line-through decoration-1' : 'font-medium text-toned'">
          {{ stop.code }}<template v-if="showBags && !stop.done"><span v-if="stop.volumes" class="font-normal text-muted"> ({{ stop.volumes }})</span><span v-else class="font-normal text-warning"> (?)</span></template>
        </span>
        <template v-if="line.hint"><span aria-hidden="true">·</span><span>{{ line.hint }}</span></template>
      </span>
      <span v-if="ride.cancel_message" class="mt-0.5 block op-micro" :class="ride.cancel_state === 'failed' ? 'font-medium text-error' : 'text-toned'" data-ride-mirror-cancel>{{ ride.cancel_message }}</span>
      <span v-if="ride.state === 'atStore' && ride.bags && !ride.undeclared.length" class="mt-1 flex items-center gap-1 op-body font-semibold text-primary">
        <NuxtIcon name="i-lucide-package-check" class="size-4" />Entregue {{ ride.bags === 1 ? "a sacola" : `as ${bagsWord(ride.bags)}` }} {{ ride.driver?.name ? `para ${ride.driver.name}` : "para o entregador" }}
      </span>
    </span>
    <NuxtButton
      v-if="ride.back_action"
      color="primary"
      icon="i-lucide-undo-2"
      :label="ride.back_action.label"
      :loading="busy"
      :disabled="!ride.back_action.enabled"
      @click.stop.prevent="emit('back')"
    />
    <NuxtIcon v-else name="i-lucide-chevron-right" class="size-5 shrink-0 text-dimmed transition group-hover:text-toned" />
  </NuxtLink>
</template>
