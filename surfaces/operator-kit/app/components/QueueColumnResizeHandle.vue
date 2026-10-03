<script setup lang="ts">
// A alça na borda de uma coluna de fila aberta (forma FILA do kit). Arrastar muda a
// largura entre esta coluna e a próxima aberta; arrastar até o fim recolhe (quem
// decide é `resizeQueueColumns`, ao soltar). Pelo teclado, as setas andam um passo.
//
// O componente não mede nem guarda nada: ele só conta o deslocamento desde o começo
// do gesto. `start` avisa para o pai medir as duas colunas; `drag` vem a cada
// movimento (prévia); `end` vem uma vez, ao soltar (é aí que o pai grava).
import { ref } from "vue";

import { QUEUE_KEYBOARD_STEP_PX } from "../presentation/queueColumns";

defineProps<{ label: string }>();

const emit = defineEmits<{ start: []; drag: [deltaPx: number]; end: [deltaPx: number] }>();

const dragging = ref(false);
let originX = 0;
let lastDelta = 0;

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0) return;
  event.preventDefault();
  dragging.value = true;
  originX = event.clientX;
  lastDelta = 0;
  (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
  emit("start");
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value) return;
  lastDelta = event.clientX - originX;
  emit("drag", lastDelta);
}

function finish(event: PointerEvent) {
  if (!dragging.value) return;
  dragging.value = false;
  (event.currentTarget as HTMLElement).releasePointerCapture?.(event.pointerId);
  emit("end", lastDelta);
}

function onKeydown(event: KeyboardEvent) {
  const step = event.key === "ArrowLeft" ? -QUEUE_KEYBOARD_STEP_PX : event.key === "ArrowRight" ? QUEUE_KEYBOARD_STEP_PX : 0;
  if (!step) return;
  event.preventDefault();
  emit("start");
  emit("end", step);
}
</script>

<template>
  <div
    role="separator"
    aria-orientation="vertical"
    tabindex="0"
    :aria-label="label"
    :title="label"
    class="group absolute inset-y-0 -right-4 z-10 hidden w-4 cursor-col-resize touch-none select-none focus-visible:outline-none lg:block"
    data-queue-resize-handle
    :data-dragging="dragging || undefined"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="finish"
    @pointercancel="finish"
    @keydown="onKeydown"
  >
    <span
      class="sticky top-1/3 mx-auto mt-24 grid h-12 w-3 place-items-center rounded-full border bg-card text-muted-foreground shadow-sm transition group-hover:border-primary/60 group-hover:text-foreground group-focus-visible:ring-2 group-focus-visible:ring-ring"
      :class="dragging ? 'border-primary text-foreground' : ''"
      aria-hidden="true"
    >
      <Icon name="lucide:grip-vertical" class="size-3" />
    </span>
  </div>
</template>
