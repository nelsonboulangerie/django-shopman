<script setup lang="ts">
// O Salão no celular: a planta não cabe na mão, então vira LISTA editável, área por
// área, com a mesma contagem da planta. Tocar numa mesa abre o mesmo painel da planta
// (lugares, forma, área, nome, capacidade, tirar do salão) numa folha de baixo; os
// botões de forma acrescentam a mesa na área escolhida. A posição na planta não se
// mexe daqui: quem desenha é o tablet ou o computador.
import { type AreaSummary, type DraftSpot, SHAPES, areaOf, seatsLabel, shortLabelOf } from "~/presentation/seating";
import type { SpotShape } from "~/types/seating";

const props = defineProps<{
  spots: readonly DraftSpot[];
  areas: readonly AreaSummary[];
  changedKeys: ReadonlySet<string>;
}>();

const emit = defineEmits<{ select: [key: string]; add: [shape: SpotShape, area: string] }>();

const activeArea = ref(props.areas[0]?.name ?? "");
watch(() => props.areas, (areas) => {
  if (!areas.some((area) => area.name === activeArea.value)) activeArea.value = areas[0]?.name ?? "";
});

const groups = computed(() =>
  props.areas.map((area) => ({ area, spots: props.spots.filter((spot) => areaOf(spot) === area.name) })),
);

function areaLine(area: AreaSummary) {
  const extras = area.extraSeats ? ` + ${area.extraSeats} extras` : "";
  return `${area.capacitySeats} ${area.capacitySeats === 1 ? "lugar" : "lugares"}${extras}`;
}
</script>

<template>
  <div class="flex flex-col gap-4 p-4" data-seating-list>
    <section class="flex flex-col gap-2" aria-label="Adicionar mesa">
      <p class="op-eyebrow text-muted-foreground">Adicionar em {{ activeArea || "Sem área" }}</p>
      <div class="grid grid-cols-4 gap-2">
        <NuxtButton
          v-for="shape in SHAPES"
          :key="shape.value"
          size="xl"
          color="neutral"
          variant="outline"
          class="h-16 flex-col justify-center gap-1 px-1"
          :aria-label="`Pôr mesa ${shape.label.toLowerCase()} em ${activeArea || 'Sem área'}`"
          :data-seating-add="shape.value"
          @click="emit('add', shape.value, activeArea === 'Sem área' ? '' : activeArea)"
        >
          <span
            class="border-2 border-foreground/40"
            :class="{
              'size-5 rounded-full': shape.value === 'round',
              'size-5 rounded-md': shape.value === 'square',
              'h-4 w-8 rounded-md': shape.value === 'long',
              'size-4 rounded-full border-[1.5px]': shape.value === 'stool',
            }"
            aria-hidden="true"
          />
          {{ shape.label }}
        </NuxtButton>
      </div>
    </section>

    <section v-for="group in groups" :key="group.area.name" class="flex flex-col gap-2" :aria-label="group.area.name">
      <NuxtButton
        color="neutral"
        variant="ghost"
        active-color="primary"
        :active="activeArea === group.area.name"
        class="justify-start -mx-2.5 items-baseline gap-2 self-start text-left"
        :aria-pressed="activeArea === group.area.name"
        @click="activeArea = group.area.name"
      >
        <span class="op-heading">{{ group.area.name }}</span>
        <span class="op-micro font-normal text-muted-foreground tabular-nums">{{ areaLine(group.area) }}</span>
      </NuxtButton>
      <p v-if="!group.spots.length" class="rounded-lg border border-dashed border-border p-3 op-micro text-muted-foreground">
        Área nova, ainda sem mesa. Toque numa forma acima para pôr a primeira.
      </p>
      <ul v-else class="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
        <li v-for="spot in group.spots" :key="spot.key">
          <NuxtButton
            color="neutral"
            variant="ghost"
            block
            class="min-h-14 justify-start gap-3 rounded-none px-3 py-2 text-left font-normal"
            :data-seating-row="spot.key"
            @click="emit('select', spot.key)"
          >
            <span
              class="grid size-10 shrink-0 place-items-center op-micro font-semibold"
              :class="[
                spot.shape === 'round' || spot.shape === 'stool' ? 'rounded-full' : 'rounded-md',
                spot.counts_in_capacity ? 'border border-foreground/30 bg-background' : 'border-2 border-dashed border-muted-foreground/70',
              ]"
              aria-hidden="true"
            >{{ shortLabelOf(spot) }}</span>
            <span class="min-w-0 flex-1">
              <span class="block truncate op-label font-semibold">{{ spot.label }}</span>
              <span class="block op-micro text-muted-foreground">
                {{ seatsLabel(spot.seats) }}{{ spot.counts_in_capacity ? "" : " · extra de dia cheio" }}
              </span>
            </span>
            <span v-if="changedKeys.has(spot.key)" class="size-2 shrink-0 rounded-full bg-primary" aria-label="mudou, falta salvar" />
            <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          </NuxtButton>
        </li>
      </ul>
    </section>
  </div>
</template>
