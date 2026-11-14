<script setup lang="ts">
// PRÉVIA (14/11) — o mapa da página Entregas: tudo o que está fora da loja ou a
// caminho dela, num desenho só.
//
// Três camadas, do fundo para a frente (dono, 14/11):
//  · NA RUA (corridas chamadas): rota e paradas em CINZA CLARO; só o entregador, a
//    moto, leva a cor e o número da corrida. O que já foi chamado sai da frente.
//  · MONTANDO: parada em branco com borda grossa na cor da corrida (a espessura do
//    traço) e o número da parada; rota pontilhada na cor. A ativa forte, as outras
//    esmaecidas. O cheio de cor fica só para a moto: ela é o destaque do mapa.
//  · ESPERANDO: o pedido sem corrida, em branco com o código. Tocar põe na ativa.
import { rideColor } from "~/presentation/ridePalette";

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
}>();
const emit = defineEmits<{ toggle: [ref: string]; fill: [place: string]; open: [number: number] }>();

const GREY = "#c9ccd1";
const GREY_STOP = "#aeb3ba";

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
const line = (pts: { latitude: number; longitude: number }[]) =>
  [props.origin, ...pts].map(xy).map((p, k) => `${k ? "L" : "M"}${p.x} ${p.y}`).join(" ");
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
  <div class="relative size-full overflow-hidden bg-[#f3ede3]" data-deliveries-map>
    <svg class="absolute inset-0 size-full" aria-hidden="true">
      <defs>
        <pattern id="deliv-streets" width="46" height="46" patternUnits="userSpaceOnUse" patternTransform="rotate(-12)">
          <path d="M46 0H0V46" fill="none" stroke="#fff" stroke-width="5" />
          <path d="M46 0H0V46" fill="none" stroke="#e4dccd" stroke-width="1" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#deliv-streets)" />
    </svg>

    <!-- as linhas: na rua (cinza) por baixo, montando (cor) por cima -->
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="absolute inset-0 size-full" aria-hidden="true">
      <path v-for="r in live" :key="`l${r.number}`" :d="line(r.stops)" fill="none" :stroke="GREY" vector-effect="non-scaling-stroke" style="stroke-width: 4px" stroke-linecap="round" stroke-linejoin="round" />
      <path
        v-for="r in building.filter((b) => b.stops.length)"
        :key="`b${r.number}`"
        :d="line(r.stops)"
        fill="none"
        :stroke="rideColor(r.number - 1).bg"
        vector-effect="non-scaling-stroke"
        style="stroke-width: 4px"
        stroke-dasharray="0.1 8"
        stroke-linecap="round"
        stroke-linejoin="round"
        :opacity="r.number === active ? 1 : 0.55"
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
        class="absolute grid size-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full op-micro font-semibold text-white shadow-sm"
        :style="{ ...at(s), background: GREY_STOP }"
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
        class="absolute z-10 grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-4 bg-white op-label font-bold tabular-nums shadow-sm transition hover:scale-110"
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

    <div class="absolute bottom-3 left-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md bg-white/90 px-2.5 py-1.5 op-micro text-toned shadow-sm">
      <span class="flex items-center gap-1"><span class="size-3 rounded-full border-2 bg-white" style="border-color:#b9a888" />Esperando</span>
      <span class="flex items-center gap-1"><span class="size-3 rounded-full border-[3px] bg-white" :style="{ borderColor: rideColor(active - 1).bg }" />Montando</span>
      <span class="flex items-center gap-1"><span class="h-1 w-4 rounded" :style="{ background: GREY }" /><NuxtIcon name="i-lucide-bike" class="size-3.5" />Na rua</span>
    </div>
  </div>
</template>
