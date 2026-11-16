<script setup lang="ts">
// O mapa da página Entregas: tudo o que está fora da loja ou a
// caminho dela, num desenho só.
//
// Três camadas, do fundo para a frente (dono, 14/11):
//  · CHAMADA (na rua): rota e borda da parada na cor da corrida, em traço CONTÍNUO
//    a 50%. O entregador é o único cheio de cor: moto sobre fundo sólido, com o
//    número (dono, 14/11, terceira rodada).
//  · EDITANDO: rota e borda da parada na cor da corrida, PONTILHADAS. A ativa
//    forte, as outras esmaecidas.
//  · AGUARDANDO: o pedido sem corrida, QUADRADO branco com o código (a parada de
//    corrida é redonda e numerada; dono, 15/11: as duas estavam parecidas). Tocar põe na ativa.
//
// O fundo é o Google Maps de verdade (dono, 14/11: "Pq não mostra um mapa de
// verdade?"), com a chave pública do navegador. As camadas acima são as nossas,
// presas ao mapa por um OverlayView: arrastar e dar zoom levam tudo junto. Sem chave,
// ou se o Google recusar, o desenho próprio (trama de ruas) fica no lugar.
import { rideColor } from "~/presentation/ridePalette";
import { metroLines } from "~/presentation/metroLines";
import type { GMap, GOverlayView } from "~/composables/useGoogleMap";

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
type LatLng = { latitude: number; longitude: number };
const props = defineProps<{
  origin: LatLng;
  waiting: MapPoint[];
  building: { number: number; stops: MapPoint[] }[];
  live: MapLiveRide[];
  active: number;
  /** Opacidade da rota e das paradas das corridas chamadas (a moto fica sempre cheia). */
  liveOpacity?: number;
  /** Sem a legenda (o mapa pequeno do detalhe). */
  bare?: boolean;
  /** A chave pública do Google Maps; vazia, o desenho próprio. */
  mapsKey?: string;
}>();
const emit = defineEmits<{ toggle: [ref: string]; fill: [place: string]; open: [number: number] }>();

const liveAlpha = computed(() => props.liveOpacity ?? 0.5);

const everyPoint = computed<LatLng[]>(() => [
  props.origin,
  ...props.waiting,
  ...props.building.flatMap((r) => r.stops),
  ...props.live.flatMap((r) => [...r.stops, ...(r.courier ? [r.courier] : [])]),
]);

// ── o desenho próprio: a caixa do mapa vira o retângulo que cabe todos os pontos ──
const bounds = computed(() => {
  const lats = everyPoint.value.map((p) => p.latitude), lngs = everyPoint.value.map((p) => p.longitude);
  const dLat = Math.max(...lats) - Math.min(...lats) || 0.01, dLng = Math.max(...lngs) - Math.min(...lngs) || 0.01;
  return { minLat: Math.min(...lats) - dLat * 0.12, maxLat: Math.max(...lats) + dLat * 0.14, minLng: Math.min(...lngs) - dLng * 0.1, maxLng: Math.max(...lngs) + dLng * 0.1 };
});
const box = ref<HTMLElement | null>(null);
const size = ref({ w: 1, h: 1 });
let observer: ResizeObserver | null = null;

// ── o mapa de verdade ──
const canvas = ref<HTMLElement | null>(null);
const layer = ref<HTMLElement | null>(null);
/** O painel do Google onde a nossa camada mora; null = desenho próprio. */
const pane = shallowRef<HTMLElement | null>(null);
/** Sobe a cada `draw()` do Google (zoom, tamanho): as posições se recalculam. */
const tick = ref(0);
let map: GMap | null = null;
let overlay: GOverlayView | null = null;
let fitted = "";
const google = useGoogleMap();
let mapLibs: Awaited<ReturnType<typeof google.load>> | null = null;
const real = computed(() => Boolean(pane.value) && !google.refused.value);

function px(p: LatLng): { x: number; y: number } {
  if (real.value && overlay) {
    void tick.value;
    const q = overlay.getProjection()?.fromLatLngToDivPixel({ lat: p.latitude, lng: p.longitude });
    if (q) return { x: q.x, y: q.y };
  }
  const b = bounds.value;
  return {
    x: ((p.longitude - b.minLng) / (b.maxLng - b.minLng)) * size.value.w,
    y: (1 - (p.latitude - b.minLat) / (b.maxLat - b.minLat)) * size.value.h,
  };
}

function fit() {
  if (!map || !mapLibs) return;
  const key = everyPoint.value.map((p) => `${p.latitude.toFixed(5)},${p.longitude.toFixed(5)}`).sort().join("|");
  if (key === fitted) return;
  fitted = key;
  const area = new mapLibs.core.LatLngBounds();
  for (const p of everyPoint.value) area.extend({ lat: p.latitude, lng: p.longitude });
  map.fitBounds(area, props.bare ? 28 : 56);
}
async function mountRealMap() {
  if (!props.mapsKey || !canvas.value) return;
  try {
    mapLibs = await google.load(props.mapsKey);
  } catch {
    return; // fica o desenho próprio
  }
  if (!canvas.value) return;
  const libs = mapLibs;
  map = new libs.maps.Map(canvas.value, {
    center: { lat: props.origin.latitude, lng: props.origin.longitude },
    zoom: 14,
    disableDefaultUI: true,
    zoomControl: !props.bare,
    clickableIcons: false,
    keyboardShortcuts: false,
    gestureHandling: "greedy",
    // Sem comércio, ônibus e rótulos de lugar: o que importa são as nossas paradas.
    styles: [
      { featureType: "poi", stylers: [{ visibility: "off" }] },
      { featureType: "transit", stylers: [{ visibility: "off" }] },
    ],
  });
  const view = new libs.maps.OverlayView();
  view.onAdd = () => {
    pane.value = view.getPanes()?.overlayMouseTarget ?? null;
  };
  view.draw = () => {
    tick.value++;
  };
  view.onRemove = () => {
    pane.value = null;
  };
  overlay = view;
  view.setMap(map);
  fit();
}
watch(layer, (el) => {
  if (el && mapLibs) mapLibs.maps.OverlayView.preventMapHitsAndGesturesFrom(el);
});
watch(everyPoint, () => fit());

onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    if (entry) size.value = { w: entry.contentRect.width, h: entry.contentRect.height };
  });
  if (box.value) observer.observe(box.value);
  void mountRealMap();
});
onBeforeUnmount(() => {
  observer?.disconnect();
  overlay?.setMap(null);
  overlay = null;
  map = null;
});

// As linhas em pixels, para correrem lado a lado onde se encontram (metrô).
const GAP = 5; // 4 px de traço + 1 de respiro
const lines = computed(() => {
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
const at = (p: LatLng) => {
  const q = px(p);
  return { left: `${q.x}px`, top: `${q.y}px` };
};

// O bairro escrito uma vez, abaixo dos seus pedidos que ainda esperam ou montam.
const places = computed(() => {
  const groups = new Map<string, { x: number; n: number; y: number }>();
  for (const p of [...props.waiting, ...props.building.flatMap((r) => r.stops)]) {
    const q = px(p), g = groups.get(p.place) || { x: 0, n: 0, y: 0 };
    groups.set(p.place, { x: g.x + q.x, n: g.n + 1, y: Math.max(g.y, q.y) });
  }
  return [...groups.entries()].map(([place, g]) => ({ place, x: g.x / g.n, y: g.y }));
});
</script>

<template>
  <div ref="box" class="relative size-full overflow-hidden bg-[#f3ede3]" data-deliveries-map :data-map-real="real ? '' : undefined">
    <div ref="canvas" class="absolute inset-0" :class="real ? '' : 'invisible'" />
    <svg v-if="!real" class="absolute inset-0 size-full" aria-hidden="true">
      <defs>
        <pattern id="deliv-streets" width="46" height="46" patternUnits="userSpaceOnUse" patternTransform="rotate(-12)">
          <path d="M46 0H0V46" fill="none" stroke="#fff" stroke-width="5" />
          <path d="M46 0H0V46" fill="none" stroke="#e4dccd" stroke-width="1" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#deliv-streets)" />
    </svg>

    <!-- A nossa camada: no painel do Google quando o mapa é o de verdade (anda com
         ele), por cima da trama quando não. As posições são em pixels nos dois. -->
    <Teleport defer :to="pane ?? box" :disabled="!real">
    <div ref="layer" :class="real ? 'absolute top-0 left-0 size-0 overflow-visible' : 'absolute inset-0'">
    <!-- as linhas: lado a lado onde se encontram, como metrô; nenhuma some -->
    <svg class="pointer-events-none absolute top-0 left-0 size-px overflow-visible" aria-hidden="true">
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

    <!-- Cada alvo de toque: um marcador de posição, o botão do kit (sem estilo
         próprio) e, dentro dele, o desenho na cor da corrida. -->
    <span
      v-for="label in places"
      :key="label.place"
      class="absolute -translate-x-1/2 translate-y-5"
      :style="{ left: `${label.x}px`, top: `${label.y}px` }"
    >
      <NuxtButton color="neutral" variant="ghost" class="p-0" :aria-label="`Pôr ${label.place} na corrida ${active}`" @click="emit('fill', label.place)">
        <span class="whitespace-nowrap rounded-full bg-white/85 px-2 py-0.5 op-micro font-semibold text-toned shadow-sm transition hover:bg-white hover:text-highlighted">{{ label.place }}</span>
      </NuxtButton>
    </span>

    <span class="absolute z-10 grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-inverted text-inverted shadow-lg ring-4 ring-white" :style="at(origin)" title="A loja">
      <NuxtIcon name="i-lucide-store" class="size-4" />
    </span>

    <!-- corrida chamada: borda contínua na cor; entregue leva o visto -->
    <template v-for="r in live" :key="`ls${r.number}`">
      <span v-for="(s, k) in r.stops" :key="s.ref" class="absolute -translate-x-1/2 -translate-y-1/2" :style="at(s)">
        <NuxtButton color="neutral" variant="ghost" class="p-0" :aria-label="`Corrida ${r.number}, parada ${k + 1}, pedido ${s.code}`" @click="emit('open', r.number)">
          <span
            class="grid size-9 place-items-center rounded-full border-4 border-solid bg-white op-label font-bold tabular-nums text-highlighted shadow-sm"
            :style="{ borderColor: `color-mix(in srgb, ${rideColor(r.number - 1).bg} ${liveAlpha * 100}%, transparent)` }"
          >
            <NuxtIcon v-if="s.done" name="i-lucide-check" class="size-3.5" /><template v-else>{{ k + 1 }}</template>
          </span>
        </NuxtButton>
      </span>
    </template>

    <!-- editando: borda pontilhada na cor da corrida -->
    <template v-for="r in building" :key="`bs${r.number}`">
      <span v-for="(s, k) in r.stops" :key="s.ref" class="absolute z-10 -translate-x-1/2 -translate-y-1/2" :style="at(s)">
        <NuxtButton color="neutral" variant="ghost" class="p-0" :aria-label="`Pedido ${s.code}, corrida ${r.number}`" @click="emit('toggle', s.ref)">
          <span class="grid size-9 place-items-center rounded-full border-4 border-dotted bg-white op-label font-bold tabular-nums text-highlighted shadow-sm transition hover:scale-110" :style="{ borderColor: rideColor(r.number - 1).bg }">{{ k + 1 }}</span>
        </NuxtButton>
      </span>
    </template>

    <!-- aguardando: quadrados brancos com o código (parada de corrida é redonda) -->
    <span v-for="o in waiting" :key="o.ref" class="absolute z-10 -translate-x-1/2 -translate-y-1/2" :style="at(o)">
      <NuxtButton color="neutral" variant="ghost" class="p-0" :aria-label="`Pedido ${o.code}, ${o.place}`" @click="emit('toggle', o.ref)">
        <span class="relative grid h-9 min-w-9 place-items-center rounded-lg border-2 border-[#b9a888] px-1.5 bg-white op-micro font-semibold tabular-nums text-toned shadow-md transition hover:scale-110">
          {{ o.code }}
          <span v-if="o.preparing" class="absolute -right-1 -bottom-1 grid size-4 place-items-center rounded-full bg-white text-toned ring-1 ring-default" title="Em preparo"><NuxtIcon name="i-lucide-chef-hat" class="size-2.5" /></span>
        </span>
      </NuxtButton>
    </span>

    <!-- o entregador: o único cheio de cor -->
    <template v-for="r in live" :key="`c${r.number}`">
      <span v-if="r.courier" class="absolute z-20 -translate-x-1/2 -translate-y-1/2" :style="at(r.courier)">
        <NuxtButton color="neutral" variant="ghost" class="p-0" :aria-label="`Entregador da corrida ${r.number}`" @click="emit('open', r.number)">
          <span class="flex items-center gap-1 rounded-full py-1 pr-2 pl-1 shadow-lg ring-2 ring-white transition hover:scale-105" :style="{ background: rideColor(r.number - 1).bg, color: rideColor(r.number - 1).fg }">
            <span class="grid size-6 place-items-center rounded-full bg-white/20"><NuxtIcon name="i-lucide-bike" class="size-4" /></span>
            <span class="op-label font-bold tabular-nums">{{ r.number }}</span>
          </span>
        </NuxtButton>
      </span>
    </template>

    </div>
    </Teleport>

    <!-- legenda pela FORMA, nunca pela cor: a cor é sempre a da corrida -->
    <div v-if="!bare" class="absolute inset-x-3 top-3 mx-auto hidden w-fit flex-wrap justify-center sm:flex items-center gap-x-3 gap-y-1 rounded-md bg-white/90 px-2.5 py-1.5 op-micro text-toned shadow-sm" data-map-legend>
      <span class="flex items-center gap-1"><span class="h-3.5 w-4 rounded-[3px] border-2 bg-white" style="border-color:#b9a888" />Aguardando</span>
      <span class="flex items-center gap-1"><svg width="16" height="6" aria-hidden="true"><path d="M2 3H15" stroke="#5f6670" stroke-width="3" stroke-dasharray="0.1 5" stroke-linecap="round" /></svg><span class="size-3.5 rounded-full border-[3px] border-dotted bg-white" style="border-color:#5f6670" />Editando</span>
      <span class="flex items-center gap-1"><svg width="16" height="6" aria-hidden="true"><path d="M1 3H15" stroke="#5f6670" stroke-width="3" stroke-linecap="round" /></svg><span class="size-3.5 rounded-full border-[3px] bg-white" style="border-color:#5f6670" />Corrida</span>
      <span class="flex items-center gap-1"><span class="grid h-4 w-6 place-items-center rounded-full bg-[#5f6670] text-white"><NuxtIcon name="i-lucide-bike" class="size-3" /></span>Entregador</span>
    </div>

  </div>
</template>
