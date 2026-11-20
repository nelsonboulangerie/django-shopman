<script setup lang="ts">
// O sheet de chamar (desenho do juiz, F5): confere e chama as corridas que a casa
// sugeriu juntar, num gesto só depois do "Chamar juntas" ou do "Chamar as 2
// corridas" do cartão de sugestões. Cada corrida com a letra e a cor dela, as
// paradas na ordem do percurso, a cotação em duas linhas (SÓ leitura: o ✔ não é
// botão; decisão 1 = A do dono), quem chega depois, o troco que sai da gaveta e a
// maquininha dela. A página é dona do estado (as corridas estão em Editando): o
// sheet só desenha e devolve os gestos.
import type { QuoteLine } from "~/presentation/deliveries";

export interface CallSheetStop {
  ref: string;
  code: string;
  customer: string;
  place: string;
  change_out_suggested_q: number;
  /** O troco como o operador vê no campo (sugerido ou o que ele digitou). */
  change: string;
}

export interface CallSheetRide {
  number: number;
  letter: string;
  color: { bg: string; fg: string };
  stops: CallSheetStop[];
  lines: QuoteLine[];
  /** "C03 chega uns 6 min depois." */
  late: string;
  needsMachine: boolean;
  machine: string;
}

const props = defineProps<{
  open: boolean;
  title: string;
  /** O total das corridas (duas linhas), só com todas cotadas. */
  lines: QuoteLine[];
  rides: CallSheetRide[];
  machineItems: { label: string; value: string }[];
  callLabel: string;
  canCall: boolean;
  reason: string;
  busy: boolean;
}>();
const emit = defineEmits<{
  close: [];
  confirm: [];
  change: [ref: string, value: string];
  machine: [number: number, value: string];
}>();

const orders = computed(() => props.rides.reduce((sum, ride) => sum + ride.stops.length, 0));
</script>

<template>
  <NuxtModal
    :open="open"
    :title="title"
    :description="`${orders} ${orders === 1 ? 'pedido' : 'pedidos'}. A corrida é paga pela casa e o frete dos clientes não muda.`"
    :close="{ class: 'min-h-11 min-w-11 justify-center' }"
    data-courier-call-sheet
    @update:open="(value: boolean) => { if (!value) emit('close'); }"
  >
    <template #body>
      <div class="flex flex-col gap-3">
        <div v-if="lines.length" class="flex flex-col gap-0.5" data-call-sheet-total>
          <p
            v-for="line in lines"
            :key="line.text"
            class="op-body tabular-nums [font-variant-emoji:text]"
            :class="line.strong ? 'font-medium text-highlighted' : 'text-muted'"
          >
            {{ line.text }}
          </p>
        </div>
        <NuxtCard v-for="ride in rides" :key="ride.number" variant="soft" data-call-sheet-ride>
          <div class="flex flex-col gap-2">
            <div class="flex items-center gap-2">
              <span
                class="grid h-6 min-w-6 shrink-0 place-items-center rounded-md px-1.5 op-micro font-bold"
                :style="{ background: ride.color.bg, color: ride.color.fg }"
              >{{ ride.letter }}</span>
              <span class="op-label font-semibold text-highlighted">Corrida {{ ride.letter }}</span>
              <span class="min-w-0 flex-1 truncate op-body text-toned">{{ ride.stops.map((stop) => stop.code).join(" → ") }}</span>
            </div>
            <div v-if="ride.lines.length" class="flex flex-col gap-0.5">
              <p
                v-for="line in ride.lines"
                :key="line.text"
                class="op-body tabular-nums [font-variant-emoji:text]"
                :class="line.strong ? 'font-medium text-highlighted' : 'text-muted'"
              >
                {{ line.text }}
              </p>
            </div>
            <p v-if="ride.late" class="op-micro text-muted">{{ ride.late }}</p>
            <ul class="flex flex-col gap-1">
              <li v-for="stop in ride.stops" :key="stop.ref" class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span class="min-w-0 flex-1 op-body"><span class="font-medium text-highlighted">{{ stop.code }} · {{ stop.customer }}</span> <span class="text-muted">· {{ stop.place }}</span></span>
                <label v-if="stop.change_out_suggested_q > 0" class="flex min-h-11 items-center gap-2" data-call-sheet-change>
                  <span class="op-micro text-toned">Troco</span>
                  <NuxtInput
                    :model-value="stop.change"
                    inputmode="decimal"
                    size="xl"
                    class="w-32"
                    :aria-label="`Troco para ${stop.code}`"
                    @update:model-value="(value: string | number) => emit('change', stop.ref, String(value ?? ''))"
                  >
                    <template #leading><span class="op-micro text-muted">R$</span></template>
                  </NuxtInput>
                </label>
              </li>
            </ul>
            <div v-if="ride.needsMachine" class="flex flex-wrap items-center gap-2" data-call-sheet-machine>
              <span class="op-body text-toned">Maquininha:</span>
              <NuxtSelect
                v-if="machineItems.length"
                :model-value="ride.machine || undefined"
                :items="machineItems"
                placeholder="Escolha"
                class="min-w-40"
                :aria-label="`Maquininha da corrida ${ride.letter}`"
                @update:model-value="(value: string) => emit('machine', ride.number, value)"
              />
              <span v-if="!ride.machine" class="op-body text-warning">Nenhuma livre</span>
            </div>
          </div>
        </NuxtCard>
        <p v-if="reason" class="op-body text-warning" data-call-sheet-reason>{{ reason }}</p>
      </div>
    </template>
    <template #footer>
      <div class="flex w-full flex-wrap justify-end gap-2">
        <NuxtButton label="Voltar" color="neutral" variant="ghost" class="min-h-11" @click="emit('close')" />
        <NuxtButton
          icon="i-lucide-bike"
          class="min-h-11"
          :label="callLabel"
          :loading="busy"
          :disabled="!canCall"
          data-call-sheet-confirm
          @click="emit('confirm')"
        />
      </div>
    </template>
  </NuxtModal>
</template>
