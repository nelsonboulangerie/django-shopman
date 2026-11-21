<script setup lang="ts">
// O sheet de chamar (desenho do juiz, F5): confere e chama as corridas, num gesto só.
// O MESMO nas três telas que chamam (#2876): a página Entregas (depois do "Chamar
// juntas" ou do "Chamar as 2 corridas" das sugestões), o cartão Pronto do Painel e o
// detalhe do pedido (aberto por UM pedido, com "Vai junto nesta corrida?").
//
// Cada corrida com a letra e a cor dela, as paradas na ordem do percurso, a cotação em
// duas linhas (SÓ leitura: o ✔ não é botão; decisão 1 = A do dono), quem chega depois
// e o que o entregador leva (troco e maquininha), com a soma do que sai da gaveta. Quem
// usa (`useCourierCall`) é dono do estado: o sheet só desenha e devolve os gestos.
//
// "Quem leva" (M3, #2526): com alguém da casa na escala, cada corrida ganha a linha de
// chips (o padrão do Admin marcado, a casa a um toque). Escolhida uma pessoa, a cotação
// vira o valor da tabela e o botão diz para quem vai. Sem ninguém, o sheet é o de antes.
import type { QuoteLine } from "~/presentation/deliveries";
import type { CarrierChip } from "~/presentation/houseCouriers";
import type { CompanionChoice } from "~/presentation/courierCall";
import type { MapPoint } from "~/components/CourierDeliveriesMap.vue";

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
  /** Os chips "Quem leva" (vazio: ninguém da casa na escala, a linha não aparece). */
  carriers: CarrierChip[];
  /** O chip marcado: "" é o serviço padrão; senão, o `ref` do entregador da casa. */
  carrier: string;
  /** "Diego está na rua. A corrida espera a volta." */
  notice: string;
  /** A lista do "Outro da casa" e quem foi escolhido nela (M3c). */
  others: { label: string; value: string }[];
  otherValue: string;
  /** "Observação para Diego (opcional)"; vazio sem a casa escolhida. */
  noteLabel: string;
  note: string;
}

/** "Vai junto nesta corrida?": só no sheet aberto por um pedido. */
export interface CallSheetCompanions {
  choices: CompanionChoice[];
  /** A cotação da sugestão da casa, em duas linhas, só leitura. */
  lines: QuoteLine[];
  late: string;
  note: { text: string; warning: boolean } | null;
}

/** O mapa simples: a loja, a rota da corrida e quem pode ir junto. */
export interface CallSheetMap {
  origin: { latitude: number; longitude: number } | null;
  building: { number: number; stops: MapPoint[] }[];
  waiting: MapPoint[];
  active: number;
  mapsKey: string;
}

const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    /** Abaixo do título; vazio, a contagem dos pedidos. */
    description?: string;
    /** O total das corridas (duas linhas), só com todas cotadas. */
    lines: QuoteLine[];
    rides: CallSheetRide[];
    companions?: CallSheetCompanions | null;
    map?: CallSheetMap | null;
    /** "Sai da gaveta: R$ 70,00 de troco." */
    drawer?: string;
    machineItems: { label: string; value: string }[];
    callLabel: string;
    /** "Chamar só A47": com companheiro marcado, o pedido sozinho num toque. */
    aloneLabel?: string;
    canCall: boolean;
    reason: string;
    busy: boolean;
  }>(),
  { description: "", companions: null, map: null, drawer: "", aloneLabel: "" },
);
const emit = defineEmits<{
  close: [];
  confirm: [];
  alone: [];
  toggle: [ref: string];
  change: [ref: string, value: string];
  machine: [number: number, value: string];
  carrier: [number: number, key: string];
  note: [number: number, value: string];
}>();

const orders = computed(() => props.rides.reduce((sum, ride) => sum + ride.stops.length, 0));
const subtitle = computed(
  () =>
    props.description ||
    `${orders.value} ${orders.value === 1 ? "pedido" : "pedidos"}. A corrida é paga pela casa e o frete dos clientes não muda.`,
);
// A cotação da sugestão vai sob o companheiro dela: o marcado, ou (cotada e mais cara
// junta) o primeiro da lista, que é sempre um companheiro da sugestão.
const suggestedRef = computed(() => {
  const choices = props.companions?.choices ?? [];
  return (choices.find((choice) => choice.suggested) ?? choices[0])?.ref ?? "";
});
const machineLabel = (value: string) => props.machineItems.find((item) => item.value === value)?.label ?? "";
</script>

<template>
  <NuxtModal
    :open="open"
    :title="title"
    :description="subtitle"
    :close="{ class: 'min-h-11 min-w-11 justify-center' }"
    data-courier-call-sheet
    @update:open="(value: boolean) => { if (!value) emit('close'); }"
  >
    <template #body>
      <div class="flex flex-col gap-3">
        <!-- O mapa simples: a loja, a rota na cor da corrida e quem pode ir junto.
             As cores seguem o tema (claro e escuro). Tocar num pino o põe na corrida. -->
        <div v-if="map" class="relative h-52 overflow-hidden rounded-xl ring-1 ring-default" data-call-sheet-map>
          <CourierDeliveriesMap
            :origin="map.origin"
            :waiting="map.waiting"
            :building="map.building"
            :live="[]"
            :active="map.active"
            :maps-key="map.mapsKey"
            bare
            @toggle="(ref: string) => emit('toggle', ref)"
          />
        </div>

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

        <!-- Vai junto nesta corrida? O companheiro da sugestão já vem marcado; a
             cotação embaixo é só leitura (decisão 1 = A do dono). -->
        <section v-if="companions" class="flex flex-col gap-2" data-call-sheet-companions>
          <p class="op-label font-semibold text-highlighted">Vai junto nesta corrida?</p>
          <NuxtCard variant="soft">
            <div class="flex flex-col gap-1">
              <div v-for="choice in companions.choices" :key="choice.ref" class="flex flex-col" data-call-sheet-companion>
                <NuxtCheckbox
                  :model-value="choice.checked"
                  :disabled="choice.disabled"
                  class="min-h-11 items-center"
                  :aria-label="`Levar ${choice.code} junto`"
                  @update:model-value="emit('toggle', choice.ref)"
                >
                  <template #label>
                    <span class="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span class="op-body font-semibold tabular-nums text-highlighted">{{ choice.code }} · {{ choice.customer }}</span>
                      <span class="op-micro text-muted">{{ [choice.place, choice.note].filter(Boolean).join(" · ") }}</span>
                      <NuxtBadge
                        v-if="choice.stage && choice.stage !== 'Pronto'"
                        color="warning"
                        icon="i-lucide-chef-hat"
                        :label="choice.stage"
                      />
                      <NuxtBadge
                        v-else-if="choice.suggested"
                        color="primary"
                        icon="i-lucide-sparkles"
                        label="Sugestão da casa"
                        data-call-sheet-suggested
                      />
                    </span>
                  </template>
                </NuxtCheckbox>
                <!-- A cotação da sugestão mora sob o companheiro dela: duas linhas, só
                     leitura; desmarcado, o ✔ continua em Juntas (decisão 1 = A). -->
                <div
                  v-if="choice.ref === suggestedRef && (companions.lines.length || companions.late)"
                  class="flex flex-col gap-0.5 ps-7 pb-1"
                  data-call-sheet-suggestion
                >
                  <p
                    v-for="line in companions.lines"
                    :key="line.text"
                    class="op-body tabular-nums [font-variant-emoji:text]"
                    :class="line.strong ? 'font-medium text-highlighted' : 'text-muted'"
                  >
                    {{ line.text }}
                  </p>
                  <p v-if="companions.late" class="op-micro text-muted">{{ companions.late }}</p>
                </div>
              </div>
              <p v-if="companions.note" class="ps-7 op-micro" :class="companions.note.warning ? 'text-warning' : 'text-muted'" data-call-sheet-companion-note>{{ companions.note.text }}</p>
            </div>
          </NuxtCard>
        </section>

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
            <RideCarrierChips
              v-if="ride.carriers.length"
              :chips="ride.carriers"
              :model-value="ride.carrier"
              :label="`Quem leva a corrida ${ride.letter}`"
              :notice="ride.notice"
              :others="ride.others"
              :other-value="ride.otherValue"
              :note-label="ride.noteLabel"
              :note="ride.note"
              @update:model-value="(key: string) => emit('carrier', ride.number, key)"
              @other="(ref: string) => emit('carrier', ride.number, ref)"
              @update:note="(value: string) => emit('note', ride.number, value)"
            />
            <div v-if="ride.lines.length" class="flex flex-col gap-0.5" data-call-sheet-quote>
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
              <li v-for="stop in ride.stops" :key="stop.ref" class="op-body">
                <span class="font-medium text-highlighted">{{ stop.code }} · {{ stop.customer }}</span> <span class="text-muted">· {{ stop.place }}</span>
              </li>
            </ul>
            <p v-if="ride.stops.length > 1" class="op-micro text-muted">O entregador sai da loja e segue esta ordem.</p>

            <!-- O que o entregador leva: o troco de cada pedido e a maquininha. -->
            <div
              v-if="ride.needsMachine || ride.stops.some((stop) => stop.change_out_suggested_q > 0)"
              class="flex flex-col gap-1 border-t border-default pt-2"
              data-call-sheet-custody
            >
              <p class="op-label font-semibold text-highlighted">O entregador leva</p>
              <template v-for="stop in ride.stops" :key="`change-${stop.ref}`">
                <label v-if="stop.change_out_suggested_q > 0" class="flex min-h-11 flex-wrap items-center justify-between gap-2" data-call-sheet-change>
                  <span class="flex items-center gap-2 op-body text-toned">
                    <NuxtIcon name="i-lucide-circle-dollar-sign" class="size-4 text-muted" />
                    Troco do pedido {{ stop.code }}
                  </span>
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
              </template>
              <div v-if="ride.needsMachine" class="flex min-h-11 flex-wrap items-center justify-between gap-2" data-call-sheet-machine>
                <span class="flex items-center gap-2 op-body text-toned">
                  <NuxtIcon name="i-lucide-credit-card" class="size-4 text-muted" />
                  Maquininha
                </span>
                <NuxtSelect
                  v-if="machineItems.length > 1"
                  :model-value="ride.machine || undefined"
                  :items="machineItems"
                  placeholder="Escolha"
                  size="xl"
                  class="min-w-40"
                  :aria-label="`Maquininha da corrida ${ride.letter}`"
                  @update:model-value="(value: string) => emit('machine', ride.number, value)"
                />
                <span v-else-if="ride.machine" class="op-body font-medium text-highlighted">{{ machineLabel(ride.machine) }}, a única livre</span>
                <span v-else class="op-body text-warning">Nenhuma livre</span>
              </div>
            </div>
          </div>
        </NuxtCard>
        <p v-if="drawer" class="op-body text-toned" data-call-sheet-drawer>{{ drawer }}</p>
        <p v-if="reason" class="op-body text-warning" data-call-sheet-reason>{{ reason }}</p>
      </div>
    </template>
    <template #footer>
      <div class="flex w-full flex-wrap justify-end gap-2">
        <NuxtButton label="Voltar" color="neutral" variant="ghost" class="min-h-11" @click="emit('close')" />
        <NuxtButton
          v-if="aloneLabel"
          color="neutral"
          variant="outline"
          class="min-h-11"
          :label="aloneLabel"
          :disabled="!canCall"
          data-call-sheet-alone
          @click="emit('alone')"
        />
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
