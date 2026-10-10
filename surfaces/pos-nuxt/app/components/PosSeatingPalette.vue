<script setup lang="ts">
// A paleta do Salão (prévia `salao-mesas4.html`, coluna da esquerda): as quatro
// formas para pôr na planta, as áreas da casa com a contagem de lugares e a legenda.
//
// A forma se ARRASTA para a planta (mouse ou dedo, Pointer Events) ou se TOCA: o
// toque põe a mesa no meio do que está visível, na área escolhida. `layout="strip"`
// (tablet) deita a mesma paleta numa faixa acima da planta, sem a legenda.
import { SHAPES, type AreaSummary } from "~/presentation/seating";
import type { SpotShape } from "~/types/seating";

const props = withDefaults(defineProps<{
  areas: readonly AreaSummary[];
  activeArea: string;
  layout?: "column" | "strip";
}>(), { layout: "column" });

const emit = defineEmits<{
  /** Começo do gesto numa forma: a página decide se é arraste ou toque. */
  grab: [shape: SpotShape, event: PointerEvent];
  selectArea: [name: string];
  addArea: [name: string];
  /** Pôr na planta a vitrine e caixa ou a entrada (elementos fixos, sem lugar). */
  addFixture: [kind: "showcase" | "entrance"];
}>();

const adding = ref(false);
const newArea = ref("");

function startAdding() {
  adding.value = true;
  newArea.value = "";
}
function confirmArea() {
  const name = newArea.value.trim();
  if (name) emit("addArea", name);
  adding.value = false;
}

function areaCount(area: AreaSummary) {
  return area.extraSeats ? `${area.capacitySeats} +${area.extraSeats}` : String(area.capacitySeats);
}
function areaAria(area: AreaSummary) {
  const extras = area.extraSeats ? ` e ${area.extraSeats} extras de dia cheio` : "";
  return `${area.name}: ${area.capacitySeats} lugares na capacidade${extras}`;
}
const isStrip = computed(() => props.layout === "strip");

/** O desenho da forma no botão (menor na faixa do tablet). */
const GLYPHS: Record<SpotShape, [string, string]> = {
  round: ["size-7 rounded-full", "size-5 rounded-full"],
  square: ["size-7 rounded-md", "size-5 rounded-sm"],
  long: ["h-5 w-10 rounded-md", "h-3.5 w-7 rounded-sm"],
  stool: ["size-5 rounded-full", "size-3.5 rounded-full"],
};
function glyphClass(shape: SpotShape) {
  return GLYPHS[shape][isStrip.value ? 1 : 0];
}
</script>

<template>
  <div
    :class="isStrip
      ? 'flex shrink-0 items-center gap-2 overflow-x-auto border-b border-border bg-card px-3 py-2 no-scrollbar *:shrink-0'
      : 'flex w-[200px] shrink-0 flex-col gap-3 overflow-y-auto border-r border-border bg-card p-3'"
    data-seating-palette
  >
    <p class="op-eyebrow text-muted-foreground">Adicionar</p>
    <div :class="isStrip ? 'flex items-center gap-2' : 'grid grid-cols-2 gap-2'">
      <NuxtButton
        v-for="shape in SHAPES"
        :key="shape.value"
        color="neutral"
        variant="outline"
        class="touch-none justify-center select-none"
        :class="isStrip ? 'gap-2' : 'h-[72px] flex-col gap-1.5'"
        :aria-label="`Pôr mesa ${shape.label.toLowerCase()} na planta`"
        :data-seating-add="shape.value"
        @pointerdown="emit('grab', shape.value, $event)"
      >
        <span
          class="shrink-0 border-2 border-foreground/40"
          :class="glyphClass(shape.value)"
          aria-hidden="true"
        />
        {{ shape.label }}
      </NuxtButton>
    </div>
    <div :class="isStrip ? 'flex items-center gap-2' : 'grid gap-1'" data-seating-fixtures>
      <NuxtButton
        v-for="fixture in [{ kind: 'showcase', label: 'Vitrine e caixa', icon: 'i-lucide-store' }, { kind: 'entrance', label: 'Entrada', icon: 'i-lucide-door-open' }] as const"
        :key="fixture.kind"
        color="neutral"
        variant="ghost"
        :icon="fixture.icon"
        :label="fixture.label"
        :aria-label="`Pôr ${fixture.label.toLowerCase()} na planta`"
        :data-seating-add-fixture="fixture.kind"
        @click="emit('addFixture', fixture.kind)"
      />
    </div>
    <p v-if="!isStrip" class="op-micro leading-4 text-muted-foreground">
      Arraste para a planta ou toque para pôr no meio. No tablet: arrastar com o dedo, pinça para zoom.
    </p>

    <div :class="isStrip ? 'mx-1 h-8 w-px bg-border' : 'h-px bg-border'" aria-hidden="true" />

    <div class="flex items-center gap-2">
      <p class="op-eyebrow text-muted-foreground" :class="isStrip ? '' : 'flex-1'">Áreas</p>
      <NuxtButton
        v-if="!adding && !isStrip"
        icon="i-lucide-plus"
        label="Área"
        variant="ghost"
        aria-label="Nova área"
        data-seating-add-area
        @click="startAdding"
      />
    </div>
    <form v-if="adding" class="flex items-center gap-1.5" @submit.prevent="confirmArea">
      <NuxtInput
        v-model="newArea"
        class="min-w-0 flex-1"
        :maxlength="40"
        placeholder="Nome da área"
        aria-label="Nome da área nova"
        autofocus
        @keydown.esc.stop="adding = false"
        @blur="confirmArea"
      />
    </form>
    <div :class="isStrip ? 'flex items-center gap-1' : 'flex flex-col gap-1'">
      <NuxtButton
        v-for="area in areas"
        :key="area.name"
        color="neutral"
        variant="ghost"
        active-color="primary" active-variant="solid"
        :active="activeArea === area.name"
        class="gap-2 text-left"
        :aria-pressed="activeArea === area.name"
        :aria-label="areaAria(area)"
        data-seating-area-row
        @click="emit('selectArea', area.name)"
      >
        <span class="op-label" :class="[activeArea === area.name ? 'font-semibold' : 'font-normal', isStrip ? '' : 'flex-1']">{{ area.name }}</span>
        <span class="op-micro font-normal text-muted-foreground tabular-nums">{{ areaCount(area) }}</span>
      </NuxtButton>
      <NuxtButton
        v-if="isStrip && !adding"
        icon="i-lucide-plus"
        label="Área"
        variant="ghost"
        aria-label="Nova área"
        @click="startAdding"
      />
    </div>

    <template v-if="!isStrip">
      <div class="flex-1" />
      <div class="rounded-lg bg-muted/60 p-2.5">
        <p class="op-micro leading-4 font-semibold text-foreground">Legenda</p>
        <p class="mt-1 flex items-center gap-2 op-micro leading-5 text-muted-foreground">
          <span class="size-3 rounded-sm border border-foreground/40 bg-card" aria-hidden="true" />conta na capacidade
        </p>
        <p class="flex items-center gap-2 op-micro leading-5 text-muted-foreground">
          <span class="size-3 rounded-sm border-2 border-dashed border-muted-foreground/70" aria-hidden="true" />extra de dia cheio
        </p>
      </div>
    </template>
  </div>
</template>
