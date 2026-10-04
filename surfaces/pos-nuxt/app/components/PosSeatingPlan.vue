<script setup lang="ts">
// A planta do salão (PDV › Ajustes › Salão, prévia `salao-mesas4.html`): o fundo de
// pontos da grade, a caixa de cada área com o rótulo e a contagem, e as mesas com as
// cadeiras desenhadas pelo número de lugares. Mesa tracejada é extra de dia cheio.
//
// Arrastar a mesa move (com o dedo no tablet, pelo Pointer Events); com "Encaixar na
// grade" ligado ela cai nos pontos. A mesa escolhida ganha os cantos e a alça de
// girar (90° por toque). Toque no fundo solta a escolha. O teclado mora na página
// (setas movem, Del tira, Esc solta), que é quem sabe se o foco está num campo.
import {
  CHAIR,
  type DraftSpot,
  PLAN_OFFSET,
  areaBoxes,
  areaTitle,
  canvasSize,
  chairCenters,
  seatsLabel,
  shortLabelOf,
  snap,
  spotSize,
} from "~/presentation/seating";

const props = defineProps<{
  spots: readonly DraftSpot[];
  selectedKey: string | null;
  zoom: number;
  snapEnabled: boolean;
}>();

const emit = defineEmits<{
  select: [key: string | null];
  /** Primeiro movimento de um arraste: a página guarda o estado para o Desfazer. */
  moveStart: [key: string];
  move: [key: string, x: number, y: number];
  rotate: [key: string];
}>();

const viewport = ref<HTMLElement | null>(null);
const size = computed(() => canvasSize(props.spots));
const areas = computed(() => areaBoxes(props.spots));

interface Drag { key: string; pointerId: number; startX: number; startY: number; originX: number; originY: number; moved: boolean }
const drag = ref<Drag | null>(null);
const dragging = computed(() => (drag.value?.moved ? props.spots.find((spot) => spot.key === drag.value!.key) ?? null : null));

function onSpotPointerDown(event: PointerEvent, spot: DraftSpot) {
  if (event.button !== 0) return;
  emit("select", spot.key);
  (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
  drag.value = { key: spot.key, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, originX: spot.x, originY: spot.y, moved: false };
}

function onSpotPointerMove(event: PointerEvent) {
  const current = drag.value;
  if (!current || current.pointerId !== event.pointerId) return;
  const dx = (event.clientX - current.startX) / props.zoom;
  const dy = (event.clientY - current.startY) / props.zoom;
  if (!current.moved) {
    if (Math.abs(dx) < 3 && Math.abs(dy) < 3) return;
    current.moved = true;
    emit("moveStart", current.key);
  }
  emit("move", current.key, snap(current.originX + dx, props.snapEnabled), snap(current.originY + dy, props.snapEnabled));
}

function onSpotPointerUp(event: PointerEvent) {
  if (drag.value?.pointerId === event.pointerId) drag.value = null;
}

/** Ponto da tela → posição na planta (para soltar uma mesa nova da paleta). Fora da planta: null. */
function toPlan(clientX: number, clientY: number): { x: number; y: number } | null {
  const element = viewport.value;
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) return null;
  return {
    x: (clientX - rect.left + element.scrollLeft) / props.zoom - PLAN_OFFSET.x,
    y: (clientY - rect.top + element.scrollTop) / props.zoom - PLAN_OFFSET.y,
  };
}

/** O meio da área visível, em coordenadas da planta (onde cai a mesa tocada na paleta). */
function visibleCenter(): { x: number; y: number } {
  const element = viewport.value;
  if (!element) return { x: 200, y: 200 };
  return {
    x: Math.max(40, (element.scrollLeft + element.clientWidth / 2) / props.zoom - PLAN_OFFSET.x),
    y: Math.max(40, (element.scrollTop + element.clientHeight / 2) / props.zoom - PLAN_OFFSET.y),
  };
}

/** A largura útil da planta na tela (para a página escolher o zoom inicial). */
function fitZoom(): number {
  const element = viewport.value;
  if (!element || !element.clientWidth) return 1;
  return Math.min(element.clientWidth / size.value.w, element.clientHeight / size.value.h);
}

defineExpose({ toPlan, visibleCenter, fitZoom });

function shapeClass(spot: DraftSpot) {
  return spot.shape === "round" || spot.shape === "stool" ? "rounded-full" : "rounded-md";
}

function spotAria(spot: DraftSpot) {
  const extra = spot.counts_in_capacity ? "" : ", extra de dia cheio";
  return `${spot.label}, ${spot.seats} ${spot.seats === 1 ? "lugar" : "lugares"}${extra}`;
}
</script>

<template>
  <div
    ref="viewport"
    class="relative min-h-0 flex-1 touch-pan-x touch-pan-y overflow-auto bg-background"
    data-seating-plan
    @pointerdown.self="emit('select', null)"
  >
    <div class="relative" :style="{ width: `${size.w * zoom}px`, height: `${size.h * zoom}px` }" @pointerdown.self="emit('select', null)">
      <div
        class="seating-dots absolute top-0 left-0 origin-top-left"
        :style="{ width: `${size.w}px`, height: `${size.h}px`, transform: `scale(${zoom})` }"
        @pointerdown.self="emit('select', null)"
      >
        <div class="absolute" :style="{ left: `${PLAN_OFFSET.x}px`, top: `${PLAN_OFFSET.y}px` }">
          <!-- áreas: o contorno das mesas de cada uma, com o rótulo e a contagem -->
          <template v-for="box in areas" :key="`area-${box.name}`">
            <div
              class="pointer-events-none absolute rounded-xl border-2"
              :class="box.allExtra ? 'border-dashed border-foreground/25' : 'border-foreground/20 bg-card/40'"
              :style="{ left: `${box.x}px`, top: `${box.y + 8}px`, width: `${box.w}px`, height: `${box.h - 8}px` }"
              data-seating-area
            />
            <span
              class="pointer-events-none absolute bg-background px-1.5 op-eyebrow whitespace-nowrap text-muted-foreground"
              :style="{ left: `${box.x + 14}px`, top: `${box.y}px` }"
            >{{ areaTitle(box) }}</span>
          </template>

          <!-- de onde a mesa saiu, enquanto é arrastada -->
          <div
            v-if="dragging && drag"
            class="pointer-events-none absolute border-2 border-dashed border-primary/40"
            :class="shapeClass(dragging)"
            :style="{
              left: `${drag.originX}px`,
              top: `${drag.originY}px`,
              width: `${spotSize(dragging.shape, dragging.seats).w}px`,
              height: `${spotSize(dragging.shape, dragging.seats).h}px`,
              transform: `rotate(${dragging.rotation}deg)`,
            }"
          />

          <div
            v-for="spot in spots"
            :key="spot.key"
            role="button"
            tabindex="0"
            class="absolute cursor-grab touch-none select-none focus-visible:outline-none active:cursor-grabbing"
            :class="selectedKey === spot.key ? 'z-10' : ''"
            :style="{
              left: `${spot.x}px`,
              top: `${spot.y}px`,
              width: `${spotSize(spot.shape, spot.seats).w}px`,
              height: `${spotSize(spot.shape, spot.seats).h}px`,
              transform: `rotate(${spot.rotation}deg)`,
            }"
            :aria-label="spotAria(spot)"
            :aria-pressed="selectedKey === spot.key"
            :data-seating-spot="spot.key"
            @pointerdown="onSpotPointerDown($event, spot)"
            @pointermove="onSpotPointerMove"
            @pointerup="onSpotPointerUp"
            @pointercancel="onSpotPointerUp"
            @focus="emit('select', spot.key)"
          >
            <span
              v-for="(chair, index) in chairCenters(spot.shape, spot.seats)"
              :key="index"
              class="absolute rounded-full border"
              :class="spot.counts_in_capacity ? 'border-foreground/25 bg-secondary' : 'border-dashed border-muted-foreground/70 bg-card'"
              :style="{ left: `${chair.x - CHAIR / 2}px`, top: `${chair.y - CHAIR / 2}px`, width: `${CHAIR}px`, height: `${CHAIR}px` }"
              aria-hidden="true"
            />
            <div
              class="absolute inset-0 grid place-items-center text-center"
              :class="[
                shapeClass(spot),
                selectedKey === spot.key
                  ? 'border-2 border-primary bg-primary/15 shadow-lg'
                  : spot.counts_in_capacity
                    ? 'border border-foreground/30 bg-card shadow-sm'
                    : 'border-2 border-dashed border-muted-foreground/70 bg-card/80',
              ]"
            >
              <div class="leading-none" :style="{ transform: `rotate(${-spot.rotation}deg)` }">
                <p :class="spot.shape === 'stool' ? 'op-micro font-semibold' : 'op-label font-semibold'">{{ shortLabelOf(spot) }}</p>
                <p v-if="spot.shape !== 'stool'" class="mt-0.5 op-micro text-muted-foreground tabular-nums">{{ seatsLabel(spot.seats) }}</p>
              </div>
            </div>
            <template v-if="selectedKey === spot.key">
              <span class="absolute -top-[5px] -left-[5px] size-2.5 rounded-sm border-2 border-primary bg-card" aria-hidden="true" />
              <span class="absolute -top-[5px] -right-[5px] size-2.5 rounded-sm border-2 border-primary bg-card" aria-hidden="true" />
              <span class="absolute -bottom-[5px] -left-[5px] size-2.5 rounded-sm border-2 border-primary bg-card" aria-hidden="true" />
              <span class="absolute -right-[5px] -bottom-[5px] size-2.5 rounded-sm border-2 border-primary bg-card" aria-hidden="true" />
              <span class="absolute left-1/2 -top-[31px] h-3 w-px bg-primary" aria-hidden="true" />
              <button
                type="button"
                class="absolute left-1/2 -top-[55px] grid size-6 -translate-x-1/2 place-items-center rounded-full border-2 border-primary bg-card text-primary before:absolute before:-inset-2.5 before:content-['']"
                :aria-label="`Girar ${spot.label} 90 graus`"
                title="Girar 90°"
                data-seating-rotate
                @pointerdown.stop
                @click.stop="emit('rotate', spot.key)"
              >
                <Icon name="lucide:rotate-cw" class="size-3.5" aria-hidden="true" />
              </button>
            </template>
          </div>

          <span
            v-if="dragging"
            class="pointer-events-none absolute z-20 inline-flex h-7 items-center gap-1.5 rounded-full bg-foreground px-2.5 op-micro font-semibold whitespace-nowrap text-background shadow"
            :style="{ left: `${dragging.x + spotSize(dragging.shape, dragging.seats).w + 16}px`, top: `${dragging.y - 22}px` }"
            aria-live="polite"
          >
            <Icon name="lucide:move" class="size-3.5" aria-hidden="true" />
            arrastando {{ shortLabelOf(dragging) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.seating-dots {
  background-color: var(--background);
  background-image: radial-gradient(color-mix(in oklab, var(--foreground) 14%, transparent) 1px, transparent 1.2px);
  background-size: 20px 20px;
}
</style>
