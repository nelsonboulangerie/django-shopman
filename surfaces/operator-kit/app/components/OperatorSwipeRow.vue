<script setup lang="ts">
// Deslizar uma linha no toque: a peça única do gesto na suíte (F7, dono 09/10/2026:
// "deslizar no mobile é sempre bom"). Nasceu no Gestor como `SwipeReveal` (só para a
// esquerda) e subiu ao kit quando ganhou o outro lado.
//
//   ← para a ESQUERDA: revela `actions` (a gaveta fica aberta depois da metade;
//     antes disso ela volta). Ex.: Atender · Recusar.
//   → para a DIREITA: faz `commit`, o gesto principal da linha, só depois do ponto de
//     compromisso (SWIPE_COMMIT_PX). Atrás da linha aparece o que vai acontecer, com
//     o verbo e o alvo ("Entregar U13 a Ana"); soltar antes devolve a linha.
//
// Regras da peça:
//   - Só no toque. Mouse não desliza (no desktop as mesmas ações moram no ⋯ e nos
//     botões do cartão), e o eixo se decide no começo: rolar nunca vira deslize.
//   - Nunca a única porta. O ato do `commit` e de cada `action` existe também num
//     botão visível do conteúdo (ou no polegar, `OperatorThumbAction`). Por isso a
//     camada de trás é `aria-hidden` e quem usa teclado ou leitor de tela segue
//     pelos botões, sem perder nada.
//   - Redução de movimento: a linha acompanha o dedo (é o próprio gesto), mas não
//     anima sozinha na volta (`motion-safe:`).
import { computed, ref } from "vue";

import {
  commitReached,
  revealSettles,
  SWIPE_LABEL_MIN_PX,
  SWIPE_REVEAL_PX,
  swipeAxis,
  swipeDirection,
  swipeOffset,
} from "../presentation/swipe";

export interface OperatorSwipeAction {
  key: string;
  label: string;
  /** Ícone no formato `lucide:nome`. */
  icon: string;
  tone: "info" | "danger";
  disabled?: boolean;
}

export interface OperatorSwipeCommit {
  /** O verbo com o alvo: "Entregar U13 a Ana", "Despachar M09". */
  label: string;
  /** Ícone no formato `lucide:nome`. */
  icon: string;
}

const props = withDefaults(
  defineProps<{
    /** O nome do que se desliza ("Pedido U13"), para quem lê a marcação. */
    label: string;
    actions?: OperatorSwipeAction[];
    commit?: OperatorSwipeCommit | null;
  }>(),
  { actions: () => [], commit: null },
);
const emit = defineEmits<{ pick: [key: string]; commit: [] }>();

const width = computed(() =>
  Math.min(SWIPE_REVEAL_PX, props.actions.length * 88),
);
const open = ref(false);
const drag = ref<{
  x0: number;
  y0: number;
  dx: number;
  axis: "x" | "y" | "";
  pointerId: number;
} | null>(null);
const base = () => (open.value ? -width.value : 0);
const offset = computed(() => (drag.value ? drag.value.dx : base()));
const armed = computed(
  () => Boolean(props.commit) && !open.value && commitReached(offset.value),
);
const showCommit = computed(() => Boolean(props.commit) && offset.value > 0);
const showActions = computed(
  () => props.actions.length > 0 && (open.value || offset.value < 0),
);

function down(event: PointerEvent) {
  if (event.pointerType === "mouse") return;
  if (!props.actions.length && !props.commit) return;
  if ((event.target as HTMLElement).closest("button, a, input, textarea, select"))
    return;
  drag.value = {
    x0: event.clientX,
    y0: event.clientY,
    dx: base(),
    axis: "",
    pointerId: event.pointerId,
  };
}
function move(event: PointerEvent) {
  const current = drag.value;
  if (!current || current.pointerId !== event.pointerId) return;
  const raw = event.clientX - current.x0;
  const axis = current.axis || swipeAxis(raw, event.clientY - current.y0);
  if (axis === "y") {
    drag.value = null;
    return;
  }
  if (axis === "x" && !current.axis) {
    // A captura é conforto (o dedo pode sair da linha); sem ela o gesto segue.
    try {
      (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
    } catch {
      /* ponteiro já solto ou sintético */
    }
  }
  const total = raw + base();
  const direction = swipeDirection(total, {
    hasActions: props.actions.length > 0,
    hasCommit: Boolean(props.commit),
    open: open.value,
  });
  const dx =
    axis !== "x" || !direction
      ? current.dx
      : direction === "left"
        ? swipeOffset(total, "left", width.value)
        : swipeOffset(total, "right");
  const wasArmed = armed.value;
  drag.value = { ...current, axis, dx: direction ? dx : 0 };
  // Um toque curto no dispositivo quando o gesto passa do ponto: o dedo sabe antes do olho.
  if (!wasArmed && armed.value) navigator.vibrate?.(8);
}
function up(event: PointerEvent) {
  const current = drag.value;
  if (!current || current.pointerId !== event.pointerId) return;
  drag.value = null;
  if (current.axis !== "x") return;
  if (!open.value && props.commit && commitReached(current.dx)) {
    emit("commit");
    return;
  }
  open.value = props.actions.length > 0 && revealSettles(current.dx, width.value);
}
function pick(action: OperatorSwipeAction) {
  open.value = false;
  if (!action.disabled) emit("pick", action.key);
}
</script>

<template>
  <!-- Parada, nenhuma camada de trás existe: o menu ⋯ do conteúdo abre por cima sem ser
       cortado. `shrink-0`: numa coluna flex que rola, a linha com `overflow-hidden`
       (durante o gesto) encolhia a zero e sumia da tela. -->
  <div
    class="relative shrink-0 rounded-lg"
    :class="showCommit || showActions ? 'overflow-hidden' : ''"
    data-swipe-row
    :data-swipe-open="open || undefined"
    :data-swipe-armed="armed || undefined"
  >
    <!-- O fundo cobre a linha; o texto mora só na faixa já descoberta e quebra linha
         nela, inteiro, em vez de ficar cortado por baixo do cartão. -->
    <div
      v-if="showCommit && commit"
      class="absolute inset-0 rounded-lg bg-primary text-sm font-semibold text-inverted"
      :class="armed ? '' : 'opacity-80'"
      aria-hidden="true"
      data-swipe-commit
    >
      <div
        class="flex h-full flex-col justify-center gap-1 px-3"
        :style="{ width: `${offset}px` }"
      >
        <Icon
          :name="armed ? 'lucide:check' : commit.icon"
          class="size-5 shrink-0"
        />
        <span v-if="offset >= SWIPE_LABEL_MIN_PX" class="break-words leading-tight">{{
          commit.label
        }}</span>
      </div>
    </div>
    <div
      v-if="showActions"
      class="absolute inset-y-0 end-0 flex"
      :style="{ width: `${width}px` }"
    >
      <div
        v-for="action in actions"
        :key="action.key"
        class="flex min-w-0 flex-1"
      >
        <NuxtButton
          type="button"
          :color="action.tone === 'danger' ? 'error' : 'info'"
          variant="solid"
          :icon="action.icon.replace('lucide:', 'i-lucide-')"
          :label="action.label"
          block
          :disabled="action.disabled"
          :tabindex="open ? 0 : -1"
          :data-swipe-action="action.key"
          @click="pick(action)"
        />
      </div>
    </div>
    <div
      class="relative touch-pan-y"
      :class="drag ? '' : 'motion-safe:transition-transform motion-safe:duration-200'"
      :style="{ transform: `translateX(${offset}px)` }"
      :data-swipe-label="label"
      @pointerdown="down"
      @pointermove="move"
      @pointerup="up"
      @pointercancel="drag = null"
    >
      <slot />
    </div>
  </div>
</template>
