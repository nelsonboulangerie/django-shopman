<script setup lang="ts">
import type {
  OperatorSwipeAction,
  OperatorSwipeCommit,
} from "../../../operator-kit/app/components/OperatorSwipeRow.vue";
import type { AffordanceRef, ZoneView } from "~/presentation/board";
import { exitGesture, exitRows, swipeHint, zoneEmptyText } from "~/presentation/board";
import type { OrderCardProjection } from "~/types/orders";

const props = withDefaults(
  defineProps<{
    zone: ZoneView;
    cards: OrderCardProjection[];
    nowMs: number;
    nextRef: string;
    phone: boolean;
    wide: boolean;
    /** Única coluna aberta do Painel: cartões em até duas colunas, para seguirem
     *  horizontais em vez de esticar na largura toda (dono, 14/11). */
    twoUp?: boolean;
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
// "Próximo" ganha o mesmo ato na ação da base (`OperatorActionBar`, desenhada pela
// página, no rodapé do painel). Os dois são o botão largo do cartão por outro
// caminho: o mesmo `action`, a mesma confirmação quando ela existe.
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
// Prontos em "A coletar" e "Saiu para entrega"; as outras colunas, sem partes.
const rows = computed(() =>
  props.zone.key === "expedition"
    ? exitRows(props.cards)
    : props.cards.map((card) => ({ card, heading: "" })),
);
const hint = computed(() =>
  swipeHint(props.zone.key, exitColumn.value ? props.cards : [], props.canOpen),
);
</script>

<template>
  <!-- No Splitter a coluna ocupa o painel (h-full, min-h-0); solta no contêiner que
       rola (abas do celular e do tablet), ela tem a altura da área visível, senão
       encolhe a zero ao lado da negociação e dos agendados. -->
  <!-- Na mesa, a coluna é um bloco só (dono, 13/11/2026, prévia `gestor-d`): fundo
       suave, cantos arredondados e o cabeçalho DENTRO dele, sem faixa nem linha. -->
  <section
    class="flex min-w-0 flex-col"
    :class="
      phone
        ? 'min-h-full flex-1 gap-3'
        : 'h-full min-h-0 w-full rounded-xl bg-elevated/60'
    "
    :data-zone="zone.key"
  >
    <header
      v-if="!phone && heading"
      class="flex h-11 shrink-0 items-center px-3"
    >
      <OrderBoardHeading
        :zone="zone"
        :cards="cards"
        :can-collapse="canCollapse"
        :shortcut="shortcut"
        @collapse="emit('collapse')"
      >
        <template #actions><slot name="heading-actions" /></template>
      </OrderBoardHeading>
    </header>

    <NuxtEmpty
      v-if="!cards.length"
      :class="phone ? undefined : 'mx-2 mb-2'"
      icon="i-lucide-circle-check"
      :title="zoneEmptyText(zone.key)"
    />

    <!-- Respiro de 8 px (com a margem negativa, os cartões ficam no mesmo alinhamento):
         o contorno do Card é um ring para fora, e o próximo a sair leva o halo de 6 px
         do KDS; sem o respiro, a área que rola os cortava no topo e na lateral (dono,
         02/11/2026). items-start: cada cartão com a altura do
         que tem; esticado até o mais alto da linha, o curto ganhava uma faixa vazia
         acima do rodapé (dono, 08/10/2026). -->
    <template v-else-if="wide || twoUp">
      <div
        class="grid min-h-0 flex-1 auto-rows-max items-start gap-2 overflow-y-auto px-2 pt-1 pb-2"
        :class="
          wide
            ? '[grid-template-columns:repeat(auto-fill,minmax(17rem,1fr))]'
            : '[grid-template-columns:repeat(auto-fill,minmax(max(17rem,calc(50%-0.25rem)),1fr))]'
        "
        data-zone-cards
      >
        <template v-for="{ card, heading: part } in rows" :key="card.ref">
        <h3
          v-if="part"
          class="col-span-full op-micro font-semibold text-muted-foreground"
          data-exit-part
        >
          {{ part }}
        </h3>
        <OrderCard
          :card="card"
          :compact="!phone"
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
        </template>
      </div>
    </template>

    <div
      v-else
      class="flex min-h-0 flex-1 flex-col overflow-y-auto"
      :class="phone ? '-mx-2 -mt-2 gap-3 px-2 pt-2 pb-3' : 'gap-2 px-2 pt-1 pb-2'"
      data-zone-cards
    >
      <template v-for="{ card, heading: part } in rows" :key="card.ref">
      <h3
        v-if="part"
        class="op-micro font-semibold text-muted-foreground"
        data-exit-part
      >
        {{ part }}
      </h3>
      <OperatorSwipeRow
        :actions="phone ? swipeActions(card) : []"
        :commit="swipeCommit(card)"
        :label="`Pedido ${card.ref}`"
        @pick="(key) => emit('swipe', card, key)"
        @commit="commitExit(card)"
      >
        <OrderCard
          :card="card"
          :compact="!phone"
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
      </template>
      <p
        v-if="phone && cards.length"
        class="flex items-center justify-center gap-1.5 py-1 op-micro text-muted-foreground"
        data-swipe-hint
      >
        <Icon name="lucide:hand" class="size-4" />{{ hint }}
      </p>
    </div>
  </section>
</template>
