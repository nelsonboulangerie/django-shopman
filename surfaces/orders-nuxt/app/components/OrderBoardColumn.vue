<script setup lang="ts">
import type {
  OperatorSwipeAction,
  OperatorSwipeCommit,
} from "../../../operator-kit/app/components/OperatorSwipeRow.vue";
import type { AffordanceRef, ZoneView } from "~/presentation/board";
import { exitGesture, swipeHint, zoneEmptyText } from "~/presentation/board";
import type { OrderCardProjection } from "~/types/orders";

const props = withDefaults(
  defineProps<{
    zone: ZoneView;
    cards: OrderCardProjection[];
    nowMs: number;
    nextRef: string;
    phone: boolean;
    wide: boolean;
    canOpen: boolean;
    selecting: boolean;
    canCollapse: boolean;
    shortcut: string;
    isBusy: (ref: string) => boolean;
    actionError: (ref: string) => string;
    isSelected: (ref: string) => boolean;
    danfePrinting: (ref: string) => boolean;
    swipeActions: (card: OrderCardProjection) => OperatorSwipeAction[];
    heading?: boolean;
  }>(),
  { heading: true },
);

const emit = defineEmits<{
  action: [ref: string, action: AffordanceRef];
  dismissError: [ref: string];
  toggleSelect: [ref: string];
  toggleAssign: [card: OrderCardProjection];
  selectMode: [ref: string];
  printDanfe: [ref: string];
  stationReady: [card: OrderCardProjection, stationRef: string];
  stationRecall: [cardRef: string, ticketPk: number];
  volumes: [cardRef: string, count: number, context: "exit" | "orders"];
  swipe: [card: OrderCardProjection, key: string];
  collapse: [];
}>();

// F7 (dono, 09/10/2026: "deslizar no mobile é sempre bom"): na Saída do celular,
// deslizar o cartão para a DIREITA faz a saída dele ("Entregar U13 a Ana"), e o
// "Próximo" ganha o mesmo ato no polegar. Os dois são o botão largo do cartão por
// outro caminho: o mesmo `action`, a mesma confirmação quando ela existe.
const exitColumn = computed(
  () => props.phone && props.zone.key === "expedition",
);
function swipeCommit(card: OrderCardProjection): OperatorSwipeCommit | null {
  if (!exitColumn.value || props.isBusy(card.ref)) return null;
  const gesture = exitGesture(card);
  return gesture ? { label: gesture.label, icon: "lucide:hand-platter" } : null;
}
function commitExit(card: OrderCardProjection) {
  const gesture = exitGesture(card);
  if (gesture && !props.isBusy(card.ref))
    emit("action", card.ref, gesture.action);
}
const thumbCard = computed(() => {
  if (!exitColumn.value) return null;
  const card = props.cards.find((c) => c.ref === props.nextRef);
  return card && exitGesture(card) ? card : null;
});
const hint = computed(() =>
  swipeHint(props.zone.key, exitColumn.value ? props.cards : [], props.canOpen),
);
</script>

<template>
  <!-- No Splitter a coluna ocupa o painel (h-full, min-h-0); solta no contêiner que
       rola (abas do celular e do tablet), ela tem a altura da área visível, senão
       encolhe a zero ao lado da negociação e dos agendados. -->
  <section
    class="flex min-w-0 flex-col gap-3"
    :class="phone ? 'min-h-full flex-1' : 'h-full min-h-0 w-full'"
    :data-zone="zone.key"
  >
    <OperatorToolbar v-if="!phone && heading" as="header">
      <OrderBoardHeading
        :zone="zone"
        :cards="cards"
        :can-collapse="canCollapse"
        :shortcut="shortcut"
        @collapse="emit('collapse')"
      />
    </OperatorToolbar>

    <NuxtEmpty
      v-if="!cards.length"
      icon="i-lucide-circle-check"
      :title="zoneEmptyText(zone.key)"
    />

    <!-- p-px: o contorno do Card é um ring 1 px para fora; sem o respiro, a área que
         rola o cortava no topo e na lateral. items-start: cada cartão com a altura do
         que tem; esticado até o mais alto da linha, o curto ganhava uma faixa vazia
         acima do rodapé (dono, 08/10/2026). -->
    <template v-else-if="wide">
      <div
        class="grid min-h-0 flex-1 auto-rows-max items-start gap-3 overflow-y-auto p-px pb-3 [grid-template-columns:repeat(auto-fill,minmax(17rem,1fr))]"
        data-zone-cards
      >
        <OrderCard
          v-for="card in cards"
          :key="card.ref"
          :card="card"
          :busy="isBusy(card.ref)"
          :error="actionError(card.ref)"
          :selected="isSelected(card.ref)"
          :selecting="selecting"
          :next="card.ref === nextRef"
          :danfe-printing="danfePrinting(card.ref)"
          :can-open="canOpen"
          @action="(action) => emit('action', card.ref, action)"
          @dismiss-error="emit('dismissError', card.ref)"
          @toggle-select="emit('toggleSelect', card.ref)"
          @toggle-assign="emit('toggleAssign', card)"
          @select-mode="emit('selectMode', card.ref)"
          @print-danfe="emit('printDanfe', card.ref)"
          @station-ready="
            (stationRef) => emit('stationReady', card, stationRef)
          "
          @station-recall="
            (ticketPk) => emit('stationRecall', card.ref, ticketPk)
          "
          @volumes="(count) => emit('volumes', card.ref, count, 'exit')"
        />
      </div>
    </template>

    <div
      v-else
      class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-px pb-3"
      data-zone-cards
    >
      <OperatorSwipeRow
        v-for="card in cards"
        :key="card.ref"
        :actions="phone ? swipeActions(card) : []"
        :commit="swipeCommit(card)"
        :label="`Pedido ${card.ref}`"
        @pick="(key) => emit('swipe', card, key)"
        @commit="commitExit(card)"
      >
        <OrderCard
          :card="card"
          :swipe-reject="phone"
          :busy="isBusy(card.ref)"
          :error="actionError(card.ref)"
          :selected="isSelected(card.ref)"
          :selecting="selecting"
          :next="card.ref === nextRef"
          :danfe-printing="danfePrinting(card.ref)"
          :can-open="canOpen"
          @action="(action) => emit('action', card.ref, action)"
          @dismiss-error="emit('dismissError', card.ref)"
          @toggle-select="emit('toggleSelect', card.ref)"
          @toggle-assign="emit('toggleAssign', card)"
          @select-mode="emit('selectMode', card.ref)"
          @print-danfe="emit('printDanfe', card.ref)"
          @station-ready="
            (stationRef) => emit('stationReady', card, stationRef)
          "
          @station-recall="
            (ticketPk) => emit('stationRecall', card.ref, ticketPk)
          "
          @volumes="
            (count) =>
              emit(
                'volumes',
                card.ref,
                count,
                zone.key === 'expedition' ? 'exit' : 'orders',
              )
          "
        />
      </OperatorSwipeRow>
      <p
        v-if="phone && cards.length"
        class="flex items-center justify-center gap-1.5 py-1 op-micro text-muted-foreground"
        data-swipe-hint
      >
        <Icon name="lucide:hand" class="size-4" />{{ hint }}
      </p>
    </div>
    <OperatorThumbAction
      v-if="thumbCard"
      :label="exitGesture(thumbCard)!.label"
      :loading="isBusy(thumbCard.ref)"
      data-exit-thumb
      @press="commitExit(thumbCard)"
    />
  </section>
</template>
