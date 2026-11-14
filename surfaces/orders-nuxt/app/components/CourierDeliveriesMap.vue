<script setup lang="ts">
// PRÉVIA (14/11) — o mapa da página Entregas: tudo o que está fora da loja ou a
// caminho dela, num desenho só.
//
// Três camadas, do fundo para a frente (dono, 14/11):
//  · CHAMADA (na rua): rota e borda da parada na cor da corrida, em traço CONTÍNUO
//    (variante: a 50%, para comparar). O entregador é o único cheio de cor: moto
//    sobre fundo sólido, com o número (dono, 14/11, terceira rodada).
//  · MONTANDO: rota e borda da parada na cor da corrida, PONTILHADAS. A ativa
//    forte, as outras esmaecidas.
//  · ESPERANDO: o pedido sem corrida, em branco com o código. Tocar põe na ativa.
import { rideColor } from "~/presentation/ridePalette";
import { metroLines } from "~/presentation/metroLines";

export interface MapPoint {
  ref: string;
  code: string;
  place: string;
  latitude: number;
  longitude: number;
  preparing?: boolean;
}
export interface MapLiveRide {
  number: number;
  stops: (MapPoint & { done?: boolean })[];
  /** Onde o entregador está (posição da TaOn); null antes do aceite. */
  courier: { latitude: number; longitude: number } | null;
  /** Ainda procurando entregador: a rota aparece, a moto não. */
  searching?: boolean;
}
const props = defineProps<{
  origin: { latitude: number; longitude: number };
  waiting: MapPoint[];
  building: { number: number; stops: MapPoint[] }[];
  live: MapLiveRide[];
  active: number;
  /** Opacidade da rota e das paradas das corridas chamadas (a moto fica sempre cheia). */
  liveOpacity?: number;
}>();
const emit = defineEmits<{ toggle: [ref: string]; fill: [place: string]; open: [number: number] }>();

const liveAlpha = computed(() => props.liveOpacity ?? 0.5);

const everyPoint = computed(() => [
  props.origin,
  ...props.waiting,
  ...props.building.flatMap((r) => r.stops),
  ...props.live.flatMap((r) => [...r.stops, ...(r.courier ? [r.courier] : [])]),
]);
const bounds = computed(() => {
  const lats = everyPoint.value.map((p) => p.latitude), lngs = everyPoint.value.map((p) => p.longitude);
  const dLat = Math.max(...lats) - Math.min(...lats) || 0.01, dLng = Math.max(...lngs) - Math.min(...lngs) || 0.01;
  return { minLat: Math.min(...lats) - dLat * 0.12, maxLat: Math.max(...lats) + dLat * 0.14, minLng: Math.min(...lngs) - dLng * 0.1, maxLng: Math.max(...lngs) + dLng * 0.1 };
});
function xy(p: { latitude: number; longitude: number }) {
  const b = bounds.value;
  return { x: ((p.longitude - b.minLng) / (b.maxLng - b.minLng)) * 100, y: (1 - (p.latitude - b.minLat) / (b.maxLat - b.minLat)) * 100 };
}
// As linhas em pixels, para correrem lado a lado onde se encontram (metrô).
const box = ref<HTMLElement | null>(null);
const size = ref({ w: 1, h: 1 });
let observer: ResizeObserver | null = null;
onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    if (entry) size.value = { w: entry.contentRect.width, h: entry.contentRect.height };
  });
  if (box.value) observer.observe(box.value);
});
onBeforeUnmount(() => observer?.disconnect());
const GAP = 5; // 4 px de traço + 1 de respiro
const lines = computed(() => {
  const px = (p: { latitude: number; longitude: number }) => {
    const q = xy(p);
    return { x: (q.x / 100) * size.value.w, y: (q.y / 100) * size.value.h };
  };
  const all = [
    ...props.live.map((r) => ({ id: r.number, points: [props.origin, ...r.stops].map(px), live: true })),
    ...props.building.filter((r) => r.stops.length).map((r) => ({ id: r.number, points: [props.origin, ...r.stops].map(px), live: false })),
  ];
  const laid = metroLines(all, GAP);
  return laid.map((l, i) => ({
    ...l,
    live: all[i]!.live,
    d: l.points.map((p, k) => `${k ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" "),
  }));
});
const at = (p: { latitude: number; longitude: number }) => ({ left: `${xy(p).x}%`, top: `${xy(p).y}%` });

// O bairro escrito uma vez, abaixo dos seus pedidos que ainda esperam ou montam.
const places = computed(() => {
  const groups = new Map<string, { x: number; n: number; y: number }>();
  for (const p of [...props.waiting, ...props.building.flatMap((r) => r.stops)]) {
    const q = xy(p), g = groups.get(p.place) || { x: 0, n: 0, y: 0 };
    groups.set(p.place, { x: g.x + q.x, n: g.n + 1, y: Math.max(g.y, q.y) });
  }
  return [...groups.entries()].map(([place, g]) => ({ place, x: g.x / g.n, y: g.y }));
});
</script>

<template>
  <div ref="box" class="relative size-full overflow-hidden bg-[#f3ede3]" data-deliveries-map>
    <svg class="absolute inset-0 size-full" aria-hidden="true">
      <defs>
        <pattern id="deliv-streets" width="46" height="46" patternUnits="userSpaceOnUse" patternTransform="rotate(-12)">
          <path d="M46 0H0V46" fill="none" stroke="#fff" stroke-width="5" />
          <path d="M46 0H0V46" fill="none" stroke="#e4dccd" stroke-width="1" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#deliv-streets)" />
    </svg>

    <!-- as linhas: lado a lado onde se encontram, como metrô; nenhuma some -->
    <svg class="absolute inset-0 size-full" aria-hidden="true">
      <path
        v-for="l in lines"
        :key="`${l.live ? 'l' : 'b'}${l.id}`"
        :d="l.d"
        fill="none"
        :stroke="rideColor(l.id - 1).bg"
        stroke-width="4"
        stroke-linecap="round"
        stroke-linejoin="round"
        :stroke-dasharray="l.live ? undefined : '0.1 8'"
        :opacity="l.live ? liveAlpha : l.id === active ? 1 : 0.55"
      />
    </svg>

    <button
      v-for="label in places"
      :key="label.place"
      type="button"
      class="absolute -translate-x-1/2 translate-y-5 whitespace-nowrap rounded-full bg-white/85 px-2 py-0.5 op-micro font-semibold text-toned shadow-sm transition hover:bg-white hover:text-highlighted"
      :style="{ left: `${label.x}%`, top: `${label.y}%` }"
      :title="`Pôr ${label.place} na corrida ${active}`"
      @click="emit('fill', label.place)"
    >{{ label.place }}</button>

    <span class="absolute z-10 grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-inverted text-inverted shadow-lg ring-4 ring-white" :style="at(origin)" title="A loja">
      <NuxtIcon name="i-lucide-store" class="size-4" />
    </span>

    <!-- na rua: paradas cinza; entregue leva o visto -->
    <template v-for="r in live" :key="`ls${r.number}`">
      <button
        v-for="(s, k) in r.stops"
        :key="s.ref"
        type="button"
        class="absolute grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-4 border-solid op-label font-bold tabular-nums text-highlighted shadow-sm"
        :style="{ ...at(s), borderColor: `color-mix(in srgb, ${rideColor(r.number - 1).bg} ${liveAlpha * 100}%, transparent)`, background: 'white' }"
        :aria-label="`Corrida ${r.number}, parada ${k + 1}, pedido ${s.code}`"
        @click="emit('open', r.number)"
      >
        <NuxtIcon v-if="s.done" name="i-lucide-check" class="size-3.5" /><template v-else>{{ k + 1 }}</template>
      </button>
    </template>

    <!-- montando: paradas cheias na cor da corrida -->
    <template v-for="r in building" :key="`bs${r.number}`">
      <button
        v-for="(s, k) in r.stops"
        :key="s.ref"
        type="button"
        class="absolute z-10 grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-4 border-dotted bg-white op-label font-bold tabular-nums shadow-sm transition hover:scale-110"
        :style="{ ...at(s), borderColor: rideColor(r.number - 1).bg, color: '#111' }"
        :aria-label="`Pedido ${s.code}, corrida ${r.number}`"
        @click="emit('toggle', s.ref)"
      >{{ k + 1 }}</button>
    </template>

    <!-- esperando: brancos com o código -->
    <button
      v-for="o in waiting"
      :key="o.ref"
      type="button"
      class="absolute z-10 grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 bg-white op-micro font-semibold tabular-nums shadow-md transition hover:scale-110"
      :style="{ ...at(o), borderColor: '#b9a888', color: '#5b4a2c' }"
      :aria-label="`Pedido ${o.code}, ${o.place}`"
      @click="emit('toggle', o.ref)"
    >
      {{ o.code }}
      <span v-if="o.preparing" class="absolute -right-1 -bottom-1 grid size-4 place-items-center rounded-full bg-white text-toned ring-1 ring-default" title="Em preparo"><NuxtIcon name="i-lucide-chef-hat" class="size-2.5" /></span>
    </button>

    <!-- o entregador: a ÚNICA coisa colorida de uma corrida que já saiu -->
    <template v-for="r in live" :key="`c${r.number}`">
      <button
        v-if="r.courier"
        type="button"
        class="absolute z-20 flex -translate-x-1/2 -translate-y-1/2 items-center gap-1 rounded-full py-1 pr-2 pl-1 shadow-lg ring-2 ring-white transition hover:scale-105"
        :style="{ ...at(r.courier), background: rideColor(r.number - 1).bg, color: rideColor(r.number - 1).fg }"
        :aria-label="`Entregador da corrida ${r.number}`"
        @click="emit('open', r.number)"
      >
        <span class="grid size-6 place-items-center rounded-full bg-white/20"><NuxtIcon name="i-lucide-bike" class="size-4" /></span>
        <span class="op-label font-bold tabular-nums">{{ r.number }}</span>
      </button>
    </template>

    <!-- legenda pela FORMA, nunca pela cor: a cor é sempre a da corrida -->
    <div class="absolute bottom-3 left-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md bg-white/90 px-2.5 py-1.5 op-micro text-toned shadow-sm" data-map-legend>
      <span class="flex items-center gap-1"><span class="size-3.5 rounded-full border-2 bg-white" style="border-color:#b9a888" />Esperando</span>
      <span class="flex items-center gap-1"><svg width="16" height="6" aria-hidden="true"><path d="M2 3H15" stroke="#5f6670" stroke-width="3" stroke-dasharray="0.1 5" stroke-linecap="round" /></svg><span class="size-3.5 rounded-full border-[3px] border-dotted bg-white" style="border-color:#5f6670" />Em montagem</span>
      <span class="flex items-center gap-1"><svg width="16" height="6" aria-hidden="true"><path d="M1 3H15" stroke="#5f6670" stroke-width="3" stroke-linecap="round" /></svg><span class="size-3.5 rounded-full border-[3px] bg-white" style="border-color:#5f6670" />Chamado</span>
      <span class="flex items-center gap-1"><span class="grid h-4 w-6 place-items-center rounded-full bg-[#5f6670] text-white"><NuxtIcon name="i-lucide-bike" class="size-3" /></span>Entregador</span>
      <span class="text-muted">· a cor é a da corrida</span>
    </div>

  </div>
</template>
