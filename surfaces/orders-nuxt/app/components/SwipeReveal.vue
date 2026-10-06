<script setup lang="ts">
// Deslizar o cartão para a esquerda revela as ações do pedido (G17, prévia v3
// `depois-gestor-celular` (a), pino 4: "Deslizar o cartão para a esquerda: Atender (o
// 'atribuir a mim' do desktop) e Recusar. A ação principal segue larga no cartão").
// O cartão acompanha o dedo; soltar além da metade deixa a gaveta aberta, antes disso
// ela volta. Só no toque (celular): no mouse as mesmas ações moram no ⋯ do cartão.
import { revealSettles, SWIPE_REVEAL_PX, swipeOffset } from "~/presentation/swipe";

export interface SwipeAction {
  key: string;
  label: string;
  icon: string;
  tone: "info" | "danger";
  disabled?: boolean;
}

const props = defineProps<{ actions: SwipeAction[]; label: string }>();
const emit = defineEmits<{ (e: "pick", key: string): void }>();

const width = computed(() => Math.min(SWIPE_REVEAL_PX, props.actions.length * 88));
const open = ref(false);
const drag = ref<{ x0: number; y0: number; dx: number; locked: "x" | "y" | "" } | null>(null);
const offset = computed(() => (drag.value ? drag.value.dx : open.value ? -width.value : 0));

function down(event: PointerEvent) {
  if (!props.actions.length || event.pointerType === "mouse") return;
  if ((event.target as HTMLElement).closest("button, a, input, textarea")) return;
  drag.value = { x0: event.clientX, y0: event.clientY, dx: open.value ? -width.value : 0, locked: "" };
}
function move(event: PointerEvent) {
  const current = drag.value;
  if (!current) return;
  const dx = event.clientX - current.x0 + (open.value ? -width.value : 0);
  const dy = event.clientY - current.y0;
  // O gesto decide a direção no começo: rolagem vertical nunca vira deslize.
  const locked = current.locked || (Math.abs(dx) > 10 ? "x" : Math.abs(dy) > 10 ? "y" : "");
  if (locked === "y") { drag.value = null; return; }
  if (locked === "x") (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
  drag.value = { ...current, locked, dx: locked === "x" ? swipeOffset(dx, "left", width.value) : current.dx };
}
function up() {
  const current = drag.value;
  drag.value = null;
  if (!current || current.locked !== "x") return;
  open.value = revealSettles(current.dx, width.value);
}
function pick(action: SwipeAction) {
  open.value = false;
  if (!action.disabled) emit("pick", action.key);
}
</script>

<template>
  <!-- Fechada, a gaveta nem existe: o menu ⋯ do cartão abre por cima sem ser cortado. -->
  <div class="relative rounded-xl" :class="open || drag ? 'overflow-hidden' : ''" data-swipe-reveal :data-swipe-open="open || undefined">
    <div v-if="open || drag" class="absolute inset-y-0 right-0 flex" :style="{ width: `${width}px` }">
      <button
        v-for="action in actions"
        :key="action.key"
        type="button"
        class="flex flex-1 flex-col items-center justify-center gap-1 text-sm font-semibold text-white disabled:opacity-60"
        :class="action.tone === 'danger' ? 'bg-destructive' : 'bg-info'"
        :disabled="action.disabled"
        :tabindex="open ? 0 : -1"
        :data-swipe-action="action.key"
        @click="pick(action)"
      >
        <Icon :name="action.icon" class="size-5" />{{ action.label }}
      </button>
    </div>
    <div
      class="relative touch-pan-y"
      :class="drag ? '' : 'transition-transform duration-200'"
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
