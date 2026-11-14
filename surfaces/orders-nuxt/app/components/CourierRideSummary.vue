<script setup lang="ts">
// A corrida montando: as paradas na ordem em que foram marcadas, o que ela pede
// (troco, maquininha), a cotação e o "Chamar". O botão mora no pé, sempre à vista.
import type { RideChoice } from "~/presentation/board";
import { MAX_RIDE_STOPS, machinesOutSentence, splitRef } from "~/presentation/board";
import type { EquipmentOptionProjection } from "~/generated/ordersContract";

const props = defineProps<{
  stops: RideChoice[];
  asksChange: RideChoice[];
  needsMachine: boolean;
  free: EquipmentOptionProjection[];
  machines: EquipmentOptionProjection[];
  quoteLine: string;
  failure: string;
  sending: boolean;
  canCall: boolean;
  /** As paradas como trajeto a partir da loja (linha do tempo). */
  timeline?: boolean;
}>();
const changeOut = defineModel<Record<string, string>>("changeOut", { required: true });
const machineRef = defineModel<string | undefined>("machineRef");
const emit = defineEmits<{ remove: [ref: string]; call: [] }>();
const code = (ref: string) => splitRef(ref).code;
</script>

<template>
  <div class="flex h-full min-h-0 flex-col" data-courier-ride-summary>
    <div class="flex items-baseline justify-between gap-2 px-4 pt-4">
      <p class="op-label font-semibold text-highlighted">A corrida</p>
      <p class="op-micro tabular-nums text-muted">{{ stops.length }} de {{ MAX_RIDE_STOPS }} paradas</p>
    </div>
    <div class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
      <div v-if="!stops.length" class="flex h-full flex-col items-center justify-center gap-2 py-6 text-center">
        <NuxtIcon name="i-lucide-route" class="size-8 text-dimmed" />
        <p class="op-body text-muted">Marque os pedidos que vão juntos.</p>
      </div>
      <ol v-else class="relative flex flex-col" :class="timeline ? 'gap-0' : 'gap-2'">
        <li v-if="timeline" class="relative flex items-center gap-3 pb-3">
          <span class="relative z-10 grid size-7 shrink-0 place-items-center rounded-full bg-inverted text-inverted"><NuxtIcon name="i-lucide-store" class="size-3.5" /></span>
          <span class="op-body text-muted">A loja</span>
          <span class="absolute top-7 bottom-0 left-3.5 w-px bg-primary/40" aria-hidden="true" />
        </li>
        <li v-for="(stop, index) in stops" :key="stop.card.ref" class="group relative flex items-start gap-3" :class="timeline ? 'pb-3' : ''">
          <span class="relative z-10 grid size-7 shrink-0 place-items-center rounded-full bg-primary op-label font-semibold tabular-nums text-inverted">{{ index + 1 }}</span>
          <span v-if="timeline && index < stops.length - 1" class="absolute top-7 bottom-0 left-3.5 w-px bg-primary/40" aria-hidden="true" />
          <span class="min-w-0 flex-1">
            <span class="block truncate op-body font-medium text-highlighted">{{ stop.label }}</span>
            <span class="block truncate op-micro text-muted">{{ [stop.place, stop.stage].filter(Boolean).join(" · ") }}</span>
          </span>
          <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" size="xs" square :aria-label="`Tirar o pedido ${code(stop.card.ref)} da corrida`" @click="emit('remove', stop.card.ref)" />
        </li>
      </ol>

      <div v-if="asksChange.length || needsMachine" class="mt-3 flex flex-col gap-3 border-t border-default pt-3">
        <NuxtFormField
          v-for="choice in asksChange"
          :key="`change-${choice.card.ref}`"
          :label="`Troco do ${code(choice.card.ref)}`"
          :description="choice.change_label || undefined"
          data-courier-ride-change
        >
          <NuxtInput v-model="changeOut[choice.card.ref]" class="w-full" type="text" inputmode="decimal" icon="i-lucide-circle-dollar-sign" :aria-label="`Troco que o entregador leva no pedido ${code(choice.card.ref)}`" />
        </NuxtFormField>
        <div v-if="needsMachine && free.length >= 2" class="flex flex-col gap-1.5" data-courier-ride-machine>
          <p class="op-body font-medium">Qual maquininha vai?</p>
          <div class="grid grid-cols-2 gap-2">
            <NuxtButton v-for="opt in free" :key="opt.ref" type="button" :label="opt.label" :color="machineRef === opt.ref ? 'primary' : 'neutral'" :variant="machineRef === opt.ref ? 'solid' : 'outline'" @click="machineRef = opt.ref" />
          </div>
        </div>
        <p v-else-if="needsMachine && !free.length" class="op-body" data-courier-ride-no-machine>
          {{ machinesOutSentence(machines) }} Tire da corrida o pedido de cartão ou espere a maquininha voltar.
        </p>
      </div>
    </div>
    <div class="flex flex-col gap-2 border-t border-default p-4">
      <NuxtAlert v-if="failure" color="error" variant="subtle" :description="failure" data-courier-ride-error />
      <p v-if="quoteLine" class="op-body font-medium tabular-nums" role="status" data-courier-ride-quote>{{ quoteLine }}</p>
      <NuxtButton block size="lg" icon="i-lucide-bike" :label="stops.length >= 2 ? `Chamar a corrida (${stops.length})` : 'Marque ao menos 2 pedidos'" :loading="sending" :disabled="!canCall" data-courier-ride-call @click="emit('call')" />
    </div>
  </div>
</template>
