<script setup lang="ts">
// O mapa da corrida: a loja e as entregas pelas coordenadas do endereço. Tocar num
// ponto marca ou desmarca o pedido. Os marcados levam o número da parada.
// PRÉVIA (14/11): desenho próprio em SVG; a versão final pode trocar o fundo pelo
// mapa do Google que o PDV já usa.
interface Point {
  ref: string;
  code: string;
  place: string;
  latitude: number;
  longitude: number;
}

const props = defineProps<{
  points: Point[];
  picked: string[];
  origin?: { latitude: number; longitude: number } | null;
  full?: boolean;
}>();
const emit = defineEmits<{ toggle: [ref: string] }>();

const bounds = computed(() => {
  const all = [...props.points, ...(props.origin ? [props.origin] : [])];
  const lats = all.map((p) => p.latitude);
  const lngs = all.map((p) => p.longitude);
  const pad = 0.15;
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs), maxLng = Math.max(...lngs);
  const dLat = Math.max(maxLat - minLat, 0.002), dLng = Math.max(maxLng - minLng, 0.002);
  return { minLat: minLat - dLat * pad, maxLat: maxLat + dLat * pad, minLng: minLng - dLng * pad, maxLng: maxLng + dLng * pad };
});
function xy(p: { latitude: number; longitude: number }) {
  const b = bounds.value;
  return {
    x: ((p.longitude - b.minLng) / (b.maxLng - b.minLng)) * 100,
    y: (1 - (p.latitude - b.minLat) / (b.maxLat - b.minLat)) * 100,
  };
}
const order = (ref: string) => props.picked.indexOf(ref);
// O bairro escrito uma vez, no meio dos seus pontos.
const places = computed(() => {
  // O nome fica abaixo do ponto mais baixo do bairro: nunca embaixo de um pino.
  const groups = new Map<string, { x: number; n: number; bottom: number }>();
  for (const point of props.points) {
    const at = xy(point);
    const g = groups.get(point.place) || { x: 0, n: 0, bottom: 0 };
    groups.set(point.place, { x: g.x + at.x, n: g.n + 1, bottom: Math.max(g.bottom, at.y) });
  }
  return [...groups.entries()].map(([name, g]) => ({ name, x: g.x / g.n, y: g.bottom }));
});
// O caminho dos marcados, a partir da loja, na ordem em que foram marcados.
const path = computed(() => {
  const stops = props.picked
    .map((ref) => props.points.find((p) => p.ref === ref))
    .filter((p): p is Point => Boolean(p));
  const chain = [...(props.origin ? [props.origin] : []), ...stops].map(xy);
  return chain.map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" ");
});
</script>

<template>
  <div class="relative overflow-hidden rounded-lg border border-default bg-[color-mix(in_oklab,var(--ui-bg-elevated)_70%,transparent)]" :class="full ? 'h-full' : 'aspect-[4/3]'" data-courier-ride-map>
    <!-- grade suave de quarteirões -->
    <svg class="absolute inset-0 size-full text-default" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <pattern id="ride-blocks" width="28" height="28" patternUnits="userSpaceOnUse">
          <path d="M28 0H0V28" fill="none" stroke="currentColor" stroke-opacity="0.07" stroke-width="1" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#ride-blocks)" />
    </svg>
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="absolute inset-0 size-full" aria-hidden="true">
      <path v-if="picked.length" :d="path" fill="none" stroke="var(--ui-primary)" stroke-width="0.6" stroke-dasharray="1.6 1.2" vector-effect="non-scaling-stroke" style="stroke-width: 2px" />
    </svg>
    <span
      v-for="place in places"
      :key="place.name"
      class="pointer-events-none absolute -translate-x-1/2 translate-y-5 whitespace-nowrap rounded bg-default/80 px-1 op-micro font-medium text-muted"
      :style="{ left: `${place.x}%`, top: `${place.y}%` }"
    >{{ place.name }}</span>
    <span
      v-if="origin"
      class="absolute grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-inverted text-inverted shadow-md ring-4 ring-default"
      :style="{ left: `${xy(origin).x}%`, top: `${xy(origin).y}%` }"
      title="A loja"
    >
      <NuxtIcon name="i-lucide-store" class="size-4" />
    </span>
    <button
      v-for="point in points"
      :key="point.ref"
      type="button"
      class="absolute grid -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full font-semibold tabular-nums shadow-sm transition focus-visible:outline-2 focus-visible:outline-primary"
      :class="order(point.ref) >= 0
        ? 'size-8 bg-primary text-inverted ring-4 ring-primary/25 op-label'
        : 'size-7 border-2 border-primary/60 bg-default text-primary op-micro hover:scale-110'"
      :style="{ left: `${xy(point).x}%`, top: `${xy(point).y}%` }"
      :aria-pressed="order(point.ref) >= 0"
      :aria-label="`Pedido ${point.code}, ${point.place}`"
      @click="emit('toggle', point.ref)"
    >
      {{ order(point.ref) >= 0 ? order(point.ref) + 1 : point.code }}
    </button>
  </div>
</template>
