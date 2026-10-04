<script setup lang="ts">
// A Saída no celular (G16, prévia v4 `cozinha-celular` (a), que a decisão §16 trouxe
// para o Gestor: "uma Saída só, no Gestor").
//
//   O mais antigo no topo
//   [ U13  Ana Ferreira            ● Próximo · pronto há 4 min ]   ← expandido
//   [ Retirada ] [ 2 volumes ]  2× Campagne · 2× Croissant · 1× Cappuccino
//   [ X36  Maria Santos · Entrega · 2 volumes · há 3 min      › ]  ← linhas de 64px
//   [ F15  João Oliveira · 🔒 Pix não confirmado: não sai ainda › ]
//   ✋ Deslize uma linha para entregar outro pedido
//   [        Entregar U13 a Ana        ]                          ← o polegar
//
// Um cartão completo só para o que está em foco; o resto é linha. Tocar a linha a traz
// para o foco; deslizar a linha para a direita faz o gesto dela (o mesmo do polegar).
// Nada decide estado aqui: o gesto é o primário do cartão (`cardAffordances`).
import type { OrderCardProjection } from "~/types/orders";
import { cardAffordances, cardClock, cardSeal, customerFirstName, packLabel, primaryVerb, sealClass, splitRef, type AffordanceRef } from "~/presentation/board";
import { SWIPE_COMMIT_PX, swipeOffset } from "~/presentation/swipe";

const props = defineProps<{
  cards: OrderCardProjection[];
  nowMs: number;
  nextRef: string;
  isBusy: (ref: string) => boolean;
  actionError: (ref: string) => string;
  canOpen: boolean;
}>();
const emit = defineEmits<{
  (e: "action", ref: string, action: AffordanceRef): void;
  (e: "dismiss-error", ref: string): void;
}>();

const picked = ref("");
const focus = computed(() => props.cards.find((card) => card.ref === picked.value) ?? props.cards[0] ?? null);
const rows = computed(() => props.cards.filter((card) => card.ref !== focus.value?.ref));

function primaryOf(card: OrderCardProjection) {
  return cardAffordances(card).find((aff) => aff.priority === "primary" || aff.disabled) ?? null;
}
/** O verbo do polegar com o código e o nome: "Entregar U13 a Ana", "Despachar M09". */
function thumbLabel(card: OrderCardProjection): string {
  const primary = primaryOf(card);
  if (!primary) return "";
  if (primary.disabled) return primary.label;
  const code = splitRef(card.ref).code;
  if (primary.ref === "advance" && card.status === "ready" && card.fulfillment_type === "pickup") {
    const name = customerFirstName(card.customer_name);
    return name ? `Entregar ${code} a ${name}` : `Entregar ${code}`;
  }
  return primaryVerb(card, primary);
}
function rowLine(card: OrderCardProjection): string {
  const parts = [card.fulfillment_label, packLabel(card), cardClock(card, props.nowMs).text].filter(Boolean);
  return parts.join(" · ");
}
function blocked(card: OrderCardProjection): string {
  const primary = primaryOf(card);
  if (!primary?.disabled) return "";
  const label = (card.advance_block_label || primary.label || "").replace(/…$/, "");
  return `${label}: não sai ainda`;
}
function act(card: OrderCardProjection) {
  const primary = primaryOf(card);
  if (!primary || primary.disabled || props.isBusy(card.ref)) return;
  emit("action", card.ref, primary.ref);
}
const items = computed(() => (focus.value?.items_summary || "").replace(/\.\.\.$/, "").split(/,\s*/).filter(Boolean));
const swipeable = computed(() => rows.value.some((card) => primaryOf(card) && !primaryOf(card)!.disabled));

// Deslizar a linha para a direita: o gesto dela, com o mesmo verbo do polegar.
const drag = ref<{ ref: string; x0: number; dx: number } | null>(null);
function down(card: OrderCardProjection, event: PointerEvent) {
  if (!primaryOf(card) || primaryOf(card)!.disabled) return;
  (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
  drag.value = { ref: card.ref, x0: event.clientX, dx: 0 };
}
function move(event: PointerEvent) {
  if (!drag.value) return;
  drag.value = { ...drag.value, dx: swipeOffset(event.clientX - drag.value.x0, "right") };
}
function up(card: OrderCardProjection) {
  const current = drag.value;
  drag.value = null;
  if (!current || current.ref !== card.ref) return;
  if (current.dx >= SWIPE_COMMIT_PX) act(card);
  else if (current.dx < 8) picked.value = card.ref;
}
const offset = (card: OrderCardProjection) => (drag.value?.ref === card.ref ? drag.value.dx : 0);
</script>

<template>
  <div class="flex min-h-full flex-col gap-2.5 pb-2" data-phone-exit>
    <p class="op-micro text-muted-foreground">O mais antigo no topo</p>

    <!-- o mais antigo, expandido -->
    <article v-if="focus" class="flex flex-col gap-2.5 rounded-xl border-2 border-primary bg-card p-3.5" :data-phone-exit-focus="focus.ref">
      <div class="flex items-start gap-2">
        <div class="min-w-0 flex-1">
          <NuxtLink v-if="canOpen" :to="`/${focus.ref}`" class="block op-code hover:underline" :aria-label="`Abrir pedido ${focus.ref}`">{{ splitRef(focus.ref).code }}</NuxtLink>
          <p v-else class="op-code">{{ splitRef(focus.ref).code }}</p>
          <p class="op-title break-words">{{ focus.customer_name || "Sem cliente" }}</p>
        </div>
        <div class="flex shrink-0 flex-col items-end gap-1 pt-1">
          <span :class="[sealClass(cardSeal(focus, { next: focus.ref === nextRef }).tone), 'inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-xs font-semibold whitespace-nowrap']">
            <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />{{ cardSeal(focus, { next: focus.ref === nextRef }).label }}
          </span>
          <span class="op-micro tnum text-muted-foreground">{{ cardClock(focus, nowMs).text }}</span>
        </div>
      </div>
      <div class="flex flex-wrap gap-2">
        <span class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-secondary px-2.5 op-body font-semibold text-secondary-foreground">
          <Icon :name="focus.fulfillment_type === 'delivery' ? 'lucide:bike' : 'lucide:store'" class="size-4" />{{ focus.fulfillment_label }}
        </span>
        <span v-if="packLabel(focus)" class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-secondary px-2.5 op-body font-semibold text-secondary-foreground tnum">
          <Icon name="lucide:package" class="size-4" />{{ packLabel(focus) }}
        </span>
      </div>
      <ul class="flex flex-col divide-y divide-border border-t border-border" data-phone-exit-items>
        <li v-for="(line, i) in items" :key="i" class="py-1.5 op-body">{{ line }}</li>
      </ul>
      <p v-if="focus.delivery_address" class="flex items-start gap-1.5 op-micro text-muted-foreground"><Icon name="lucide:map-pin" class="mt-0.5 size-3.5 shrink-0" />{{ focus.delivery_address }}</p>
      <p v-if="blocked(focus)" class="flex items-start gap-1.5 rounded-md border border-destructive/30 bg-destructive/12 px-2.5 py-1.5 op-label" data-phone-exit-block>
        <Icon name="lucide:lock" class="mt-0.5 size-4 shrink-0 text-destructive" />{{ focus.advance_block_reason || blocked(focus) }}
      </p>
      <div v-if="actionError(focus.ref)" class="flex items-start gap-1.5 rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1.5 text-xs text-destructive" role="alert">
        <span class="min-w-0 flex-1">{{ actionError(focus.ref) }}</span>
        <button type="button" class="grid size-control shrink-0 place-items-center rounded hover:bg-destructive/20" aria-label="Dispensar aviso" @click="emit('dismiss-error', focus.ref)">
          <Icon name="lucide:x" class="size-3.5" />
        </button>
      </div>
    </article>

    <!-- os outros: linhas de 64px; tocar traz para o foco, deslizar entrega -->
    <div
      v-for="card in rows"
      :key="card.ref"
      class="relative overflow-hidden rounded-xl"
      :data-phone-exit-row="card.ref"
    >
      <div class="absolute inset-0 flex items-center gap-2 bg-primary px-4 op-label font-semibold text-primary-foreground" aria-hidden="true">
        <Icon name="lucide:hand-platter" class="size-5" />{{ thumbLabel(card) }}
      </div>
      <button
        type="button"
        class="relative flex min-h-16 w-full touch-pan-y items-center gap-3 rounded-xl border bg-card px-3.5 text-left transition-transform"
        :class="blocked(card) ? 'border-destructive/40' : 'border-border'"
        :style="{ transform: `translateX(${offset(card)}px)` }"
        :aria-label="`${splitRef(card.ref).code}, ${card.customer_name || 'sem cliente'}. Tocar para ver; deslizar para ${thumbLabel(card) || 'abrir'}`"
        @pointerdown="down(card, $event)"
        @pointermove="move"
        @pointerup="up(card)"
        @pointercancel="drag = null"
        @keydown.enter.prevent="picked = card.ref"
      >
        <span class="w-14 shrink-0 op-title font-bold tnum">{{ splitRef(card.ref).code }}</span>
        <span class="min-w-0 flex-1">
          <span class="block op-body font-semibold">{{ card.customer_name || "Sem cliente" }}</span>
          <span v-if="blocked(card)" class="flex items-center gap-1 op-micro font-semibold text-destructive"><Icon name="lucide:lock" class="size-3.5" />{{ blocked(card) }}</span>
          <span v-else class="block op-micro text-muted-foreground">{{ rowLine(card) }}</span>
        </span>
        <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
      </button>
    </div>

    <p v-if="swipeable" class="flex items-center justify-center gap-1.5 op-micro text-muted-foreground" data-phone-exit-hint>
      <Icon name="lucide:hand" class="size-4" />Deslize uma linha para entregar outro pedido
    </p>

    <!-- o gesto no polegar: preso logo acima da barra de seções (4rem + área segura) -->
    <div v-if="focus && primaryOf(focus)" class="h-16 shrink-0" aria-hidden="true" />
    <div v-if="focus && primaryOf(focus)" class="fixed inset-x-3 bottom-[calc(4rem+env(safe-area-inset-bottom)+0.75rem)] z-20 md:hidden">
      <button
        type="button"
        class="flex h-14 w-full items-center justify-center gap-2 rounded-xl op-action font-semibold transition"
        :class="primaryOf(focus)!.disabled
          ? 'cursor-default border-2 border-dashed border-border bg-card text-muted-foreground'
          : 'bg-primary text-primary-foreground shadow-lg hover:bg-primary/90 active:scale-[0.98] disabled:opacity-60'"
        :disabled="isBusy(focus.ref) || primaryOf(focus)!.disabled"
        data-phone-exit-thumb
        @click="act(focus)"
      >
        <Icon :name="primaryOf(focus)!.disabled ? 'lucide:lock' : 'lucide:hand-platter'" class="size-5" />{{ thumbLabel(focus) }}
      </button>
    </div>
  </div>
</template>
