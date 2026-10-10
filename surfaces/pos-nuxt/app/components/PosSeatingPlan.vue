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
import type { SeatingFixtureKind, SeatingFixtureProjection } from "~/types/seating";

const props = defineProps<{
  spots: readonly DraftSpot[];
  selectedKey: string | null;
  zoom: number;
  snapEnabled: boolean;
  /** A vitrine e caixa e a entrada (v4): desenho que orienta, sem lugar. */
  fixtures?: readonly SeatingFixtureProjection[];
  /** Mesa → comanda aberta nela (vínculo opcional comanda × mesa). */
  occupied?: Record<string, string>;
}>();

const emit = defineEmits<{
  select: [key: string | null];
  /** Primeiro movimento de um arraste: a página guarda o estado para o Desfazer. */
  moveStart: [key: string];
  move: [key: string, x: number, y: number];
  rotate: [key: string];
  fixtureMoveStart: [kind: SeatingFixtureKind];
  moveFixture: [kind: SeatingFixtureKind, x: number, y: number];
  rotateFixture: [kind: SeatingFixtureKind];
  removeFixture: [kind: SeatingFixtureKind];
  /** Pinça no tablet ("No tablet: pinça para zoom", v4): a razão desde o começo do gesto. */
  pinch: [ratio: number, phase: "start" | "move"];
}>();

const viewport = ref<HTMLElement | null>(null);
const size = computed(() => {
  const base = canvasSize(props.spots);
  let { w, h } = base;
  for (const fixture of props.fixtures || []) {
    w = Math.max(w, PLAN_OFFSET.x + fixture.plan_x + fixture.width + 40);
    h = Math.max(h, PLAN_OFFSET.y + fixture.plan_y + fixture.height + 40);
  }
  return { w, h };
});
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

// ── Elementos fixos: arrastar move; tocar escolhe (girar, tirar). ──
interface FixtureDrag { kind: SeatingFixtureKind; pointerId: number; startX: number; startY: number; originX: number; originY: number; moved: boolean }
const fixtureDrag = ref<FixtureDrag | null>(null);
const selectedFixture = ref<SeatingFixtureKind | null>(null);
function onFixturePointerDown(event: PointerEvent, fixture: SeatingFixtureProjection) {
  if (event.button !== 0) return;
  emit("select", null);
  selectedFixture.value = fixture.kind;
  (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
  fixtureDrag.value = { kind: fixture.kind, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, originX: fixture.plan_x, originY: fixture.plan_y, moved: false };
}
function onFixturePointerMove(event: PointerEvent) {
  const current = fixtureDrag.value;
  if (!current || current.pointerId !== event.pointerId) return;
  const dx = (event.clientX - current.startX) / props.zoom;
  const dy = (event.clientY - current.startY) / props.zoom;
  if (!current.moved) {
    if (Math.abs(dx) < 3 && Math.abs(dy) < 3) return;
    current.moved = true;
    emit("fixtureMoveStart", current.kind);
  }
  emit("moveFixture", current.kind, snap(current.originX + dx, props.snapEnabled), snap(current.originY + dy, props.snapEnabled));
}
function onFixturePointerUp(event: PointerEvent) {
  if (fixtureDrag.value?.pointerId === event.pointerId) fixtureDrag.value = null;
}
watch(() => props.selectedKey, (key) => { if (key) selectedFixture.value = null; });

// ── Pinça para zoom (dois dedos na planta). O arraste de mesa já é de um dedo só. ──
let pinchStart = 0;
function touchDistance(event: TouchEvent): number {
  const [a, b] = [event.touches[0], event.touches[1]];
  if (!a || !b) return 0;
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
}
function onTouchStart(event: TouchEvent) {
  if (event.touches.length !== 2) return;
  pinchStart = touchDistance(event);
  drag.value = null;
  fixtureDrag.value = null;
  if (pinchStart > 0) emit("pinch", 1, "start");
}
function onTouchMove(event: TouchEvent) {
  if (event.touches.length !== 2 || !pinchStart) return;
  event.preventDefault();
  const distance = touchDistance(event);
  if (distance > 0) emit("pinch", distance / pinchStart, "move");
}
function onTouchEnd(event: TouchEvent) {
  if (event.touches.length < 2) pinchStart = 0;
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
    @pointerdown.self="emit('select', null); selectedFixture = null"
    @touchstart.passive="onTouchStart"
    @touchmove="onTouchMove"
    @touchend.passive="onTouchEnd"
    @touchcancel.passive="onTouchEnd"
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

          <!-- ELEMENTOS FIXOS (v4): a vitrine e caixa (faixa cinza com o nome em pé) e
               a entrada (um vão com o nome embaixo). Arrastar move; tocar escolhe. -->
          <div
            v-for="fixture in fixtures || []"
            :key="`fixture-${fixture.kind}`"
            role="button"
            tabindex="0"
            class="absolute cursor-grab touch-none select-none"
            :class="selectedFixture === fixture.kind ? 'z-10' : ''"
            :style="{ left: `${fixture.plan_x}px`, top: `${fixture.plan_y}px`, width: `${fixture.width}px`, height: `${fixture.height}px` }"
            :aria-label="fixture.label"
            :data-seating-fixture="fixture.kind"
            @pointerdown="onFixturePointerDown($event, fixture)"
            @pointermove="onFixturePointerMove"
            @pointerup="onFixturePointerUp"
            @pointercancel="onFixturePointerUp"
          >
            <div
              v-if="fixture.kind === 'showcase'"
              class="grid size-full place-items-center rounded-md border bg-muted"
              :class="selectedFixture === fixture.kind ? 'border-2 border-primary' : 'border-foreground/20'"
            >
              <span class="op-micro whitespace-nowrap text-muted-foreground" :class="fixture.height > fixture.width ? '[writing-mode:vertical-rl]' : ''">{{ fixture.label }}</span>
            </div>
            <div v-else class="relative size-full">
              <span class="absolute inset-x-0 top-1/2 border-t-2 border-dashed" :class="selectedFixture === fixture.kind ? 'border-primary' : 'border-foreground/40'" aria-hidden="true" />
              <span class="absolute top-full left-1/2 -translate-x-1/2 bg-background px-1 op-micro whitespace-nowrap text-muted-foreground">{{ fixture.label }}</span>
            </div>
            <div v-if="selectedFixture === fixture.kind" class="absolute -top-11 left-1/2 flex -translate-x-1/2 gap-1 rounded-md border border-border bg-card p-1 shadow" @pointerdown.stop>
              <NuxtButton icon="i-lucide-rotate-cw" color="neutral" variant="ghost" square :aria-label="`Girar ${fixture.label}`" @click.stop="emit('rotateFixture', fixture.kind)" />
              <NuxtButton icon="i-lucide-trash-2" color="error" variant="ghost" square :aria-label="`Tirar ${fixture.label} da planta`" @click.stop="emit('removeFixture', fixture.kind); selectedFixture = null" />
            </div>
          </div>

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
            <span
              v-if="spot.ref && occupied?.[spot.ref]"
              class="absolute -top-2 -right-2 grid size-6 place-items-center rounded-full bg-primary text-primary-foreground shadow"
              :title="`Comanda ${occupied[spot.ref]} aberta nesta mesa`"
              :data-seating-occupied="spot.ref"
            >
              <Icon name="lucide:receipt-text" class="size-3.5" aria-hidden="true" />
            </span>
            <template v-if="selectedKey === spot.key">
              <span class="absolute -top-[5px] -left-[5px] size-2.5 rounded-sm border-2 border-primary bg-card" aria-hidden="true" />
              <span class="absolute -top-[5px] -right-[5px] size-2.5 rounded-sm border-2 border-primary bg-card" aria-hidden="true" />
              <span class="absolute -bottom-[5px] -left-[5px] size-2.5 rounded-sm border-2 border-primary bg-card" aria-hidden="true" />
              <span class="absolute -right-[5px] -bottom-[5px] size-2.5 rounded-sm border-2 border-primary bg-card" aria-hidden="true" />
              <span class="absolute left-1/2 -top-[31px] h-3 w-px bg-primary" aria-hidden="true" />
              <!-- A alça de girar da planta: um círculo de 24 px colado na mesa, com a
                   área de toque ampliada pelo `before` (44 px). -->
              <NuxtButton
                icon="i-lucide-rotate-cw"
                color="neutral"
                variant="outline"
                square
                class="absolute left-1/2 -top-[55px] size-6 -translate-x-1/2 justify-center rounded-full p-0 text-primary ring-2 ring-primary before:absolute before:-inset-2.5 before:content-['']"
                :ui="{ leadingIcon: 'size-3.5' }"
                :aria-label="`Girar ${spot.label} 90 graus`"
                title="Girar 90°"
                data-seating-rotate
                @pointerdown.stop
                @click.stop="emit('rotate', spot.key)"
              />
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
