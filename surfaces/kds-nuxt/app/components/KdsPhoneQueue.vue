<script setup lang="ts">
// A estação no celular (prévia v4, `cozinha-celular4.html` (b)): UM ticket inteiro em
// foco ("Agora"), os seguintes em linhas compactas ("Próximo", "Depois"), e o resto da
// fila vira número e agregado ("+2 na fila · A fazer: 6× Cappuccino"). O botão do
// ticket em foco desce para a barra do polegar (`#kds-thumb`, na página).
//
// Tocar uma linha traz aquele ticket para o foco (com o botão dele no polegar): todo
// ato continua a um toque de distância, sem cards minúsculos.
import type { KDSTicketProjection } from "~/types/kds";
import {
  elapsedLabel,
  queueLine,
  splitRef,
  type KDSAllDayCount,
  type KDSDensity,
} from "~/presentation/board";

const props = defineProps<{
  cards: KDSTicketProjection[];
  nextPk: number | null;
  blockedRefs: ReadonlySet<string>;
  additionPks: ReadonlySet<number>;
  finishingPks: ReadonlySet<number>;
  serviceDate: string;
  today: string;
  allDay: KDSAllDayCount[];
  density: KDSDensity;
}>();
const emit = defineEmits<{
  open: [pk: number];
  start: [pk: number];
  finish: [pk: number];
  undo: [pk: number];
  blocked: [];
  locked: [pk: number];
}>();

const ROWS = 3;
const chosenPk = ref<number | null>(null);
const focus = computed<KDSTicketProjection | null>(() => {
  const chosen = props.cards.find((card) => card.pk === chosenPk.value);
  return chosen ?? props.cards[0] ?? null;
});
const others = computed(() => props.cards.filter((card) => card.pk !== focus.value?.pk));
// "+N na fila" abre a fila inteira em linhas (nenhum ticket fica a mais de um toque).
const showAll = ref(false);
const rows = computed(() => (showAll.value ? others.value : others.value.slice(0, ROWS)));
const rest = computed(() => (showAll.value ? [] : others.value.slice(ROWS)));
const allDayLine = computed(() =>
  props.allDay
    .slice(0, 2)
    .map((entry) => `${entry.qty}× ${entry.name}`)
    .join(", "),
);

function rowLabel(index: number): string {
  return index === 0 ? "Próximo" : "Depois";
}
function rowLocked(card: KDSTicketProjection): boolean {
  return props.blockedRefs.has(card.order_ref) || Boolean(card.finish_block_label);
}
</script>

<template>
  <div class="flex flex-col gap-2" data-kds-phone-queue>
    <KdsTicketCard
      v-if="focus"
      :key="focus.pk"
      :ticket="focus"
      :density="density"
      eyebrow="Agora"
      action-target="#kds-thumb"
      :next="serviceDate === today && focus.pk === nextPk"
      :blocked="blockedRefs.has(focus.order_ref)"
      :addition="additionPks.has(focus.pk)"
      :finishing="finishingPks.has(focus.pk)"
      :service-date="serviceDate"
      @open="emit('open', focus.pk)"
      @start="emit('start', focus.pk)"
      @finish="emit('finish', focus.pk)"
      @undo="emit('undo', focus.pk)"
      @blocked="emit('blocked')"
      @locked="emit('locked', focus.pk)"
    />

    <button
      v-for="(card, index) in rows"
      :key="card.pk"
      type="button"
      class="flex min-h-16 w-full items-center gap-3 rounded-xl border bg-card px-3.5 text-left transition hover:bg-accent active:bg-accent/70"
      :class="rowLocked(card) ? 'border-destructive/40' : 'border-border'"
      :aria-label="`Trazer o pedido ${splitRef(card.order_ref).code} para o foco`"
      data-kds-queue-row
      @click="chosenPk = card.pk"
    >
      <span class="w-16 shrink-0 op-micro text-muted-foreground">{{ rowLabel(index) }}</span>
      <b class="w-12 shrink-0 text-lg tabular-nums">{{ splitRef(card.order_ref).code }}</b>
      <span class="min-w-0 flex-1 truncate text-sm font-semibold">{{ queueLine(card) }}</span>
      <span
        v-if="rowLocked(card)"
        class="inline-flex shrink-0 items-center gap-1 op-micro font-semibold text-destructive"
      >
        <Icon name="lucide:lock" class="size-3.5" />Bloqueado
      </span>
      <span v-else-if="!card.is_scheduled" class="shrink-0 text-base font-bold tabular-nums text-muted-foreground">
        {{ elapsedLabel(card.elapsed_seconds) }}
      </span>
    </button>

    <button
      v-if="rest.length"
      type="button"
      class="min-h-11 w-full rounded-lg text-center op-label text-muted-foreground transition hover:bg-accent"
      :aria-label="`Ver a fila inteira: mais ${rest.length} pedidos`"
      data-kds-queue-rest
      @click="showAll = true"
    >
      <b class="tabular-nums text-foreground">+{{ rest.length }} na fila</b>
      <template v-if="allDayLine"> · A fazer: {{ allDayLine }}</template>
    </button>
    <p v-else-if="allDayLine" class="text-center op-label text-muted-foreground">A fazer: {{ allDayLine }}</p>
  </div>
</template>
