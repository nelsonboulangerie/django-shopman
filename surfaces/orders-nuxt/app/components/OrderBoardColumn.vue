<script setup lang="ts">
import type { SwipeAction } from "~/components/SwipeReveal.vue";
import type { AffordanceRef, ZoneView } from "~/presentation/board";
import { zoneEmptyText } from "~/presentation/board";
import type { OrderCardProjection } from "~/types/orders";

withDefaults(
  defineProps<{
    zone: ZoneView;
    cards: OrderCardProjection[];
    nowMs: number;
    nextRef: string;
    phone: boolean;
    wide: boolean;
    canOpen: boolean;
    selecting: boolean;
    fulfillment: string;
    exitFilterTabs: { value: string; label: string; icon: string }[];
    layoutMemory: string;
    layoutMemoryTitle: string;
    canCollapse: boolean;
    shortcut: string;
    isBusy: (ref: string) => boolean;
    actionError: (ref: string) => string;
    isSelected: (ref: string) => boolean;
    danfePrinting: (ref: string) => boolean;
    swipeActions: (card: OrderCardProjection) => SwipeAction[];
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
  updateFulfillment: [value: string | number];
}>();
</script>

<template>
  <section
    class="flex h-full min-h-0 min-w-0 flex-col gap-3"
    :data-zone="zone.key"
  >
    <NuxtDashboardToolbar v-if="!phone && heading" as="header">
      <OrderBoardHeading
        :zone="zone"
        :cards="cards"
        :wide="wide"
        :fulfillment="fulfillment"
        :exit-filter-tabs="exitFilterTabs"
        :layout-memory="layoutMemory"
        :layout-memory-title="layoutMemoryTitle"
        :can-collapse="canCollapse"
        :shortcut="shortcut"
        @update-fulfillment="emit('updateFulfillment', $event)"
        @collapse="emit('collapse')"
      />
    </NuxtDashboardToolbar>

    <NuxtEmpty
      v-if="!cards.length"
      icon="i-lucide-circle-check"
      :title="zoneEmptyText(zone.key)"
    />

    <template v-else-if="wide">
      <div
        class="grid min-h-0 flex-1 gap-3 overflow-y-auto pb-3 [grid-template-columns:repeat(auto-fill,minmax(17rem,1fr))]"
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
      class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pb-3"
      data-zone-cards
    >
      <SwipeReveal
        v-for="card in cards"
        :key="card.ref"
        :actions="phone ? swipeActions(card) : []"
        :label="`Pedido ${card.ref}`"
        @pick="(key) => emit('swipe', card, key)"
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
      </SwipeReveal>
      <p
        v-if="phone && cards.length"
        class="flex items-center justify-center gap-1.5 py-1 op-micro text-muted-foreground"
        data-swipe-hint
      >
        <Icon name="lucide:hand" class="size-4" />{{
          !canOpen
            ? "Puxe para atualizar"
            : zone.key === "intake"
              ? "Deslize para Atender ou Recusar · puxe para atualizar"
              : "Deslize para Atender · puxe para atualizar"
        }}
      </p>
    </div>
  </section>
</template>
