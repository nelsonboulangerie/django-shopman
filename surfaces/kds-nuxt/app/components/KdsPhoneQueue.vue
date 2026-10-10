<script setup lang="ts">
// A estação no celular (prévia v4, `cozinha-celular4.html` (b)): UM ticket inteiro em
// foco ("Agora"), os seguintes em linhas compactas ("Próximo", "Depois"), e o resto da
// fila vira número e agregado ("+2 na fila · A fazer: 6× Cappuccino"). O ato do ticket
// em foco está na ação na base da página (`OperatorActionBar`, "Pronto W07").
//
// Tocar uma linha traz aquele ticket para o foco (com o ato dele na base): todo ato
// continua a um toque de distância, sem cards minúsculos. Deslizar uma linha para a
// direita marca Pronto (F7, `OperatorSwipeRow` do kit), e ela vem para o foco com o
// Desfazer. O toque LONGO (no ticket em foco ou numa linha) abre o menu do pedido:
// ver o pedido, desfazer, reabrir (nota 7).
import type { OperatorSwipeCommit } from "../../../operator-kit/app/components/OperatorSwipeRow.vue";
import type { KDSTicketProjection } from "~/types/kds";
import {
  elapsedLabel,
  queueLine,
  queuePositionLabel,
  splitRef,
  ticketAction,
  type KDSAllDayCount,
  type KDSDensity,
} from "~/presentation/board";

const props = defineProps<{
  cards: KDSTicketProjection[];
  /** O ticket em foco (a página escolhe: o tocado, ou o primeiro da fila). */
  focusPk: number | null;
  nextPk: number | null;
  blockedRefs: ReadonlySet<string>;
  additionPks: ReadonlySet<number>;
  finishingPks: ReadonlySet<number>;
  /** O prazo de cada Desfazer aberto (epoch ms). */
  finishUntil?: ReadonlyMap<number, number>;
  allDay: KDSAllDayCount[];
  density: KDSDensity;
  /** O aviso no bolso está ligado: o pedido novo toca e vibra com a tela apagada. */
  pushOn?: boolean;
}>();
const emit = defineEmits<{
  choose: [pk: number];
  open: [pk: number];
  undo: [pk: number];
  finish: [pk: number];
  hold: [pk: number];
}>();

const ROWS = 3;
const focus = computed<KDSTicketProjection | null>(
  () => props.cards.find((card) => card.pk === props.focusPk) ?? props.cards[0] ?? null,
);
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

// A linha logo abaixo do foco é a "Próximo"; as outras, "Depois" (a mesma régua da mesa).
function rowLabel(index: number): string {
  return queuePositionLabel(index + 1);
}
function rowLocked(card: KDSTicketProjection): boolean {
  return props.blockedRefs.has(card.order_ref) || Boolean(card.finish_block_label);
}
/** Deslizar para Pronto só quando o Pronto pode sair agora (em preparo, sem trava). */
function rowCommit(card: KDSTicketProjection): OperatorSwipeCommit | null {
  const action = ticketAction(card, {
    armed: true,
    blocked: props.blockedRefs.has(card.order_ref),
    finishing: props.finishingPks.has(card.pk),
  });
  if (action.kind !== "finish") return null;
  return { label: `Pronto ${splitRef(card.order_ref).code}`, icon: "lucide:check" };
}
function onCommit(pk: number) {
  emit("finish", pk);
  emit("choose", pk);
}

// Um manipulador de toque longo por linha (a linha guarda qual pedido segurou).
const heldPk = ref<number | null>(null);
const rowLongPress = useLongPress(() => {
  if (heldPk.value != null) emit("hold", heldPk.value);
});
function onRowPointerdown(pk: number, event: PointerEvent) {
  heldPk.value = pk;
  rowLongPress.onPointerdown(event);
}
</script>

<template>
  <div class="flex flex-col gap-2" data-kds-phone-queue>
    <KdsTicketCard
      v-if="focus"
      :key="focus.pk"
      :ticket="focus"
      :density="density"
      :eyebrow="queuePositionLabel(0)"
      action-in-bar
      :next="focus.pk === nextPk"
      :blocked="blockedRefs.has(focus.order_ref)"
      :addition="additionPks.has(focus.pk)"
      :finishing="finishingPks.has(focus.pk)"
      :finish-until="finishUntil?.get(focus.pk)"
      @open="emit('open', focus.pk)"
      @undo="emit('undo', focus.pk)"
      @hold="emit('hold', focus.pk)"
    />

    <OperatorSwipeRow
      v-for="(card, index) in rows"
      :key="card.pk"
      :label="`Pedido ${splitRef(card.order_ref).code}`"
      :commit="rowCommit(card)"
      @commit="onCommit(card.pk)"
    >
      <div
        role="button"
        tabindex="0"
        class="flex min-h-16 w-full touch-manipulation select-none items-center gap-3 rounded-lg border bg-default px-3.5 text-left transition hover:bg-elevated active:bg-elevated focus-visible:outline-2 focus-visible:outline-primary"
        :class="rowLocked(card) ? 'border-error/40' : 'border-default'"
        :aria-label="`Trazer o pedido ${splitRef(card.order_ref).code} para o foco. Toque longo: ver o pedido, desfazer, reabrir`"
        data-kds-queue-row
        @pointerdown="onRowPointerdown(card.pk, $event)"
        @pointermove="rowLongPress.onPointermove"
        @pointerup="rowLongPress.onPointerup"
        @pointercancel="rowLongPress.onPointercancel"
        @pointerleave="rowLongPress.onPointerleave"
        @click.capture="rowLongPress.onClickCapture"
        @contextmenu="rowLongPress.onContextmenu"
        @click="emit('choose', card.pk)"
        @keydown.enter.prevent="emit('choose', card.pk)"
        @keydown.space.prevent="emit('choose', card.pk)"
      >
        <span class="w-16 shrink-0 op-micro text-muted-foreground">{{ rowLabel(index) }}</span>
        <b class="w-12 shrink-0 text-lg tabular-nums">{{ splitRef(card.order_ref).code }}</b>
        <span class="min-w-0 flex-1 break-words text-sm font-semibold">{{ queueLine(card) }}</span>
        <span
          v-if="rowLocked(card)"
          class="inline-flex shrink-0 items-center gap-1 op-micro font-semibold text-error"
        >
          <Icon name="lucide:lock" class="size-3.5" />Bloqueado
        </span>
        <span v-else class="shrink-0 text-base font-bold tabular-nums text-muted-foreground">
          {{ elapsedLabel(card.elapsed_seconds) }}
        </span>
      </div>
    </OperatorSwipeRow>

    <NuxtButton
      v-if="rest.length"
      color="neutral"
      variant="ghost"
      block
      class="justify-center whitespace-normal text-center"
      :aria-label="`Ver a fila inteira: mais ${rest.length} pedidos`"
      data-kds-queue-rest
      @click="showAll = true"
    >
      <span>
        <b class="tabular-nums text-highlighted">+{{ rest.length }} na fila</b>
        <template v-if="allDayLine"> · A fazer: {{ allDayLine }}</template>
      </span>
    </NuxtButton>
    <p v-else-if="allDayLine" class="text-center op-label text-muted-foreground">A fazer: {{ allDayLine }}</p>
    <p class="text-center op-micro text-muted-foreground" data-kds-hold-hint>
      Deslize uma linha para a direita: Pronto. Toque longo: ver o pedido, desfazer, reabrir.
    </p>
    <p v-if="pushOn" class="text-center op-micro text-muted-foreground" data-kds-push-on>
      Este celular toca e vibra com pedido novo mesmo com a tela apagada.
    </p>
  </div>
</template>
