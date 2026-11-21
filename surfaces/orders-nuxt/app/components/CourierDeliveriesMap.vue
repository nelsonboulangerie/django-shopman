<script setup lang="ts">
// O mapa da página Entregas: tudo o que está fora da loja ou a
// caminho dela, num desenho só.
//
// Três camadas, do fundo para a frente (dono, 14/11):
// A parada de corrida é um OCTÓGONO, como placa de trânsito, com o número na tinta
// da corrida (`ink`: o mesmo matiz escurecido até ler sobre branco; dono, 16/11).
//  · CHAMADA (na rua): fundo branco; rota e borda em traço CONTÍNUO, a 50%. A parada já entregue
//    fica SÓLIDA na cor, com o visto na cor de texto dela (dono, 16/11). O entregador:
//    moto sobre fundo sólido, com a letra da corrida (dono, 14/11, terceira rodada; letra desde 16/11).
//  · EDITANDO: fundo em listras finas na cor; rota e borda PONTILHADAS. A ativa
//    forte, as outras esmaecidas. As listras separam a corrida que se monta da que
//    já está na rua (dono, 16/11).
//  · AGUARDANDO: o pedido sem corrida, REDONDO, preto e branco, com o código. A forma
//    e a falta de cor separam o que espera do que já tem corrida (dono, 15 e 16/11).
//    Tocar põe na ativa.
//
// O fundo é o Google Maps de verdade (dono, 14/11: "Pq não mostra um mapa de
// verdade?"), com a chave pública do navegador. As camadas acima são as nossas,
// presas ao mapa por um OverlayView: arrastar e dar zoom levam tudo junto. Sem chave,
// ou se o Google recusar, o desenho próprio (trama de ruas) fica no lugar.
//
// Legível e tocável (revisão das Entregas, 16/11/2026, F7a): toda parada leva a LETRA
// da corrida num selo no canto (a cor nunca vem sozinha); a linha tem um contorno na
// tinta da corrida por baixo, para o amarelo e o laranja lerem sobre o papel; as cores
// do mapa são fixas por tema (acompanham o claro e o escuro, dono 17/11); todo alvo tem 44 px; pinos no
// mesmo ponto se abrem em círculo; o enquadramento não corre atrás da moto e, depois
// que o operador mexe no mapa, "Ver tudo" devolve o quadro inteiro. Loja sem
// coordenada não se desenha (antes ia parar na casa de um cliente).
import { rideColor } from "~/presentation/ridePalette";
import { PIN_TEXT, fitKey, googleMapStyles, lineOutline, mapTokens, spreadOverlaps } from "~/presentation/deliveriesMap";
import { rideLetter } from "~/presentation/deliveries";
import { metroLines } from "~/presentation/metroLines";
import { courierPositionAge } from "~/presentation/courierPosition";
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
  /** Onde o entregador estava na última posição e a hora dela; null antes do aceite. */
  courier: { latitude: number; longitude: number; at?: string } | null;
  /** Ainda procurando entregador: a rota aparece, a moto não. */
  searching?: boolean;
}
/** A corrida que a casa sugere juntar (ride_plan): rota tracejada cinza, ainda não montada. */
export interface MapSuggestedRide {
  key: string;
  /** "A47 + C03 · R$ 16,50" (os códigos e, cotada, o preço das juntas). */
  label: string;
  stops: MapPoint[];
}
type LatLng = { latitude: number; longitude: number };
const props = defineProps<{
  /** A loja; null quando ela não tem coordenada (a rota começa na primeira parada). */
  origin: LatLng | null;
  waiting: MapPoint[];
  building: { number: number; stops: MapPoint[] }[];
  live: MapLiveRide[];
  /** As sugestões visíveis no cartão de Aguardando; somem com "Agora não" ou ao virar corrida. */
  suggested?: MapSuggestedRide[];
  active: number;
  /** Opacidade da rota e das paradas das corridas chamadas (a moto fica sempre cheia). */
  liveOpacity?: number;
  /** Sem a legenda (o mapa pequeno do detalhe). */
  bare?: boolean;
  /** A chave pública do Google Maps; vazia, o desenho próprio. */
  mapsKey?: string;
}>();
const emit = defineEmits<{ toggle: [ref: string]; fill: [place: string]; open: [number: number] }>();

// O tema da tela decide as cores do mapa (dono, 17/11).
const colorMode = useColorMode();
const dark = computed(() => colorMode.value === "dark");
const tokens = computed(() => mapTokens(dark.value));
const liveAlpha = computed(() => props.liveOpacity ?? 0.5);
const OCTAGON = "32.8,24.1 24.1,32.8 11.9,32.8 3.2,24.1 3.2,11.9 11.9,3.2 24.1,3.2 32.8,11.9";

/** O que se entrega e a loja: o que decide o enquadramento. */
const framePoints = computed<LatLng[]>(() => [
  ...(props.origin ? [props.origin] : []),
  ...props.waiting,
  ...props.building.flatMap((r) => r.stops),
  ...props.live.flatMap((r) => r.stops),
]);
const everyPoint = computed<LatLng[]>(() => [
  ...framePoints.value,
  ...props.live.flatMap((r) => (r.courier ? [r.courier] : [])),
]);

// ── o desenho próprio: a caixa do mapa vira o retângulo que cabe todos os pontos ──
const bounds = computed(() => {
  const lats = everyPoint.value.map((p) => p.latitude), lngs = everyPoint.value.map((p) => p.longitude);
  const dLat = Math.max(...lats) - Math.min(...lats) || 0.01, dLng = Math.max(...lngs) - Math.min(...lngs) || 0.01;
  return { minLat: Math.min(...lats) - dLat * 0.12, maxLat: Math.max(...lats) + dLat * 0.14, minLng: Math.min(...lngs) - dLng * 0.1, maxLng: Math.max(...lngs) + dLng * 0.1 };
});
const box = ref<HTMLElement | null>(null);
const size = ref({ w: 1, h: 1 });
// No mapa estreito (celular) a legenda aberta cobriria pinos: ela começa recolhida num
// botão no canto e abre por cima do mapa só quando o operador pede (#2908).
const LEGEND_INLINE_MIN_WIDTH = 560;
const legendCollapsible = computed(() => size.value.w < LEGEND_INLINE_MIN_WIDTH);
const legendOpen = ref(false);
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
/** O operador arrastou ou deu zoom: o mapa para de se reenquadrar sozinho. */
const userMoved = ref(false);
let programmatic = false;
const google = useGoogleMap();
let mapLibs: Awaited<ReturnType<typeof google.load>> | null = null;
const real = computed(() => Boolean(pane.value) && !google.refused.value);
// A faixa do topo é da legenda (aberta no mapa largo, o botão "Legenda" no estreito): o
// quadro começa abaixo dela, para nenhum pino ficar escondido por baixo (#2908).
const LEGEND_BAND = 64;
// A legenda aberta pode quebrar em duas linhas (o item "Sugestão" aparece com sugestão):
// a faixa acompanha a altura medida dela, com o mesmo respiro.
const legendHeight = ref(0);
let legendObserver: ResizeObserver | null = null;
function observeLegend(el: unknown) {
  legendObserver?.disconnect();
  legendObserver = null;
  if (!(el instanceof HTMLElement)) {
    legendHeight.value = 0;
    return;
  }
  legendObserver = new ResizeObserver(([entry]) => {
    if (entry) legendHeight.value = entry.contentRect.height;
  });
  legendObserver.observe(el);
}
const topBand = computed(() => {
  if (props.bare) return 0;
  if (legendCollapsible.value) return LEGEND_BAND;
  return Math.max(LEGEND_BAND, Math.round(legendHeight.value) + 32);
});

function px(p: LatLng): { x: number; y: number } {
  if (real.value && overlay) {
    void tick.value;
    const q = overlay.getProjection()?.fromLatLngToDivPixel({ lat: p.latitude, lng: p.longitude });
    if (q) return { x: q.x, y: q.y };
  }
  const b = bounds.value;
  return {
    x: ((p.longitude - b.minLng) / (b.maxLng - b.minLng)) * size.value.w,
    y: topBand.value + (1 - (p.latitude - b.minLat) / (b.maxLat - b.minLat)) * (size.value.h - topBand.value),
  };
}

function fit(force = false) {
  if (!map || !mapLibs) return;
  const key = fitKey(framePoints.value);
  if (!force && (key === fitted || userMoved.value)) return;
  fitted = key;
  const area = new mapLibs.core.LatLngBounds();
  for (const p of everyPoint.value) area.extend({ lat: p.latitude, lng: p.longitude });
  programmatic = true;
  map.fitBounds(area, props.bare ? 28 : { top: 56 + topBand.value, right: 56, bottom: 56, left: 56 });
}
function showAll() {
  userMoved.value = false;
  fit(true);
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
    center: { lat: (props.origin ?? framePoints.value[0])?.latitude ?? 0, lng: (props.origin ?? framePoints.value[0])?.longitude ?? 0 },
    zoom: 14,
    disableDefaultUI: true,
    zoomControl: !props.bare,
    clickableIcons: false,
    keyboardShortcuts: false,
    gestureHandling: "greedy",
    // Sem comércio, ônibus e rótulos de lugar; no escuro, o papel escuro.
    styles: googleMapStyles(dark.value),
    // O fundo por baixo dos blocos de imagem: sem isto o Google usa o cinza-claro
    // dele, que vaza nas emendas entre os blocos e risca o mapa escuro de linhas.
    backgroundColor: tokens.value.paper,
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
  map.addListener("dragstart", () => {
    userMoved.value = true;
  });
  map.addListener("zoom_changed", () => {
    if (!programmatic) userMoved.value = true;
  });
  map.addListener("idle", () => {
    programmatic = false;
  });
  fit();
}
watch(layer, (el) => {
  if (el && mapLibs) mapLibs.maps.OverlayView.preventMapHitsAndGesturesFrom(el);
});
watch(framePoints, () => fit());
// Trocar o tema com a tela aberta repinta o Google sem recriar o mapa.
// O fundo só se escolhe ao criar o mapa; na troca, repinta-se a div que o Google
// criou dentro do canvas (é nela que ele grava o `backgroundColor`).
watch(dark, (value) => {
  map?.setOptions({ styles: googleMapStyles(value) });
  const inner = canvas.value?.firstElementChild;
  if (map && inner instanceof HTMLElement) inner.style.backgroundColor = mapTokens(value).paper;
});

onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    if (entry) size.value = { w: entry.contentRect.width, h: entry.contentRect.height };
  });
  if (box.value) observer.observe(box.value);
  void mountRealMap();
});
onBeforeUnmount(() => {
  observer?.disconnect();
  legendObserver?.disconnect();
  overlay?.setMap(null);
  overlay = null;
  map = null;
});

// As linhas em pixels, para correrem lado a lado onde se encontram (metrô).
const GAP = 5; // 4 px de traço + 1 de respiro
const lines = computed(() => {
  const all = [
    ...props.live.map((r) => ({ id: r.number, points: [...(props.origin ? [props.origin] : []), ...r.stops].map(px), live: true })),
    ...props.building.filter((r) => r.stops.length).map((r) => ({ id: r.number, points: [...(props.origin ? [props.origin] : []), ...r.stops].map(px), live: false })),
  ];
  const laid = metroLines(all, GAP);
  return laid.map((l, i) => ({
    ...l,
    live: all[i]!.live,
    d: l.points.map((p, k) => `${k ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" "),
  }));
});
// A rota que a casa sugere: da loja pelas paradas, na ordem do plano, e a etiqueta acima
// do meio das paradas. Fica por baixo das corridas e nunca recebe toque (o gesto mora no cartão).
const ghosts = computed(() =>
  (props.suggested ?? [])
    .filter((g) => g.stops.length > 0)
    .map((g) => {
      // No pino de verdade: pinos próximos se abrem em círculo, e a rota vai até onde eles estão.
      const stops = g.stops.map((stop) => {
        const q = px(stop), d = offsets.value.get(stop.ref) || { dx: 0, dy: 0 };
        return { x: q.x + d.dx, y: q.y + d.dy };
      });
      const points = [...(props.origin ? [px(props.origin)] : []), ...stops];
      const top = Math.min(...stops.map((p) => p.y));
      return {
        key: g.key,
        label: g.label,
        d: points.map((p, k) => `${k ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" "),
        x: stops.reduce((sum, p) => sum + p.x, 0) / stops.length,
        y: top,
      };
    }),
);
// Pinos no mesmo ponto se abrem em círculo: cada um com o seu toque.
const offsets = computed(() =>
  spreadOverlaps([
    ...props.waiting.map((o) => ({ key: o.ref, ...px(o) })),
    ...props.building.flatMap((r) => r.stops.map((s) => ({ key: s.ref, ...px(s) }))),
    ...props.live.flatMap((r) => [
      ...r.stops.map((s) => ({ key: s.ref, ...px(s) })),
      ...(r.courier ? [{ key: `courier:${r.number}`, ...px(r.courier), w: 64, h: 40 }] : []),
    ]),
  ]),
);
const at = (p: LatLng, key = "") => {
  const q = px(p);
  const d = (key && offsets.value.get(key)) || { dx: 0, dy: 0 };
  return { left: `${q.x + d.dx}px`, top: `${q.y + d.dy}px` };
};
const MARKER = "absolute -translate-x-1/2 -translate-y-1/2 hover:z-30 focus-within:z-30";

// A idade da posição de cada moto (F7b): passada de 2 min sem posição nova, ela esmaece e
// diz desde quando estava ali. O relógio anda a cada segundo, sem esperar a releitura.
const nowMs = useNowTick();
const courierAge = (r: MapLiveRide) => courierPositionAge(r.courier?.at, nowMs.value);
// A etiqueta da moto perto da borda (celular, 375 px) sai do quadro se ficar centrada: cada
// desenho a empurra para dentro da caixa do mapa, com 4 px de folga.
function keepInside(el: unknown) {
  if (!(el instanceof HTMLElement) || !box.value) return;
  el.style.marginLeft = "0px";
  const frame = box.value.getBoundingClientRect(), chip = el.getBoundingClientRect();
  const shift = Math.max(frame.left + 4 - chip.left, Math.min(0, frame.right - 4 - chip.right));
  if (shift) el.style.marginLeft = `${shift}px`;
}

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
  <div ref="box" class="relative size-full overflow-hidden" :style="{ background: tokens.paper }" data-deliveries-map :data-map-real="real ? '' : undefined">
    <div ref="canvas" class="absolute inset-0" :class="real ? '' : 'invisible'" />
    <svg v-if="!real" class="absolute inset-0 size-full" aria-hidden="true">
      <defs>
        <pattern id="deliv-streets" width="46" height="46" patternUnits="userSpaceOnUse" patternTransform="rotate(-12)">
          <path d="M46 0H0V46" fill="none" :stroke="tokens.street" stroke-width="5" />
          <path d="M46 0H0V46" fill="none" :stroke="tokens.streetEdge" stroke-width="1" />
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
      <!-- a sugestão da casa: tracejado longo cinza, por baixo de tudo (prévia 2A, #2874) -->
      <path
        v-for="g in ghosts"
        :key="`g${g.key}`"
        :d="g.d"
        fill="none"
        :stroke="tokens.neutral"
        stroke-width="4"
        stroke-dasharray="11 8"
        stroke-linecap="round"
        stroke-linejoin="round"
        opacity="0.75"
        :data-map-suggestion="g.key"
      />
      <!-- o contorno na tinta da corrida, por baixo: o amarelo e o laranja leem sobre o papel -->
      <path
        v-for="l in lines"
        :key="`o${l.live ? 'l' : 'b'}${l.id}`"
        :d="l.d"
        fill="none"
        :stroke="lineOutline(tokens, rideColor(l.id - 1))"
        stroke-width="7"
        stroke-linecap="round"
        stroke-linejoin="round"
        :stroke-dasharray="l.live ? undefined : '0.1 8'"
        :opacity="l.live ? 0.85 : l.id === active ? 1 : 0.55"
        data-line-outline
      />
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
      <NuxtButton color="neutral" variant="ghost" class="min-h-11 p-0" :aria-label="active ? `Pôr ${label.place} na corrida ${rideLetter(active)}` : `Pôr ${label.place} numa corrida nova`" @click="emit('fill', label.place)">
        <span class="whitespace-nowrap rounded-full px-2 py-0.5 op-micro font-semibold shadow-sm" :style="{ background: tokens.chip, color: tokens.text }">{{ label.place }}</span>
      </NuxtButton>
    </span>

    <!-- a etiqueta da sugestão, acima das paradas dela: só leitura (o gesto mora no cartão) -->
    <span
      v-for="g in ghosts"
      :key="`gl${g.key}`"
      class="pointer-events-none absolute -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-full border border-dashed px-2 py-0.5 op-micro font-semibold shadow-sm"
      :style="{ left: `${g.x}px`, top: `${g.y - 22}px`, background: tokens.chip, color: tokens.text, borderColor: tokens.neutral }"
      aria-hidden="true"
      :data-map-suggestion-label="g.key"
    >{{ g.label }}</span>

    <span v-if="origin" class="absolute z-10 grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full shadow-lg ring-4 ring-white" :style="{ ...at(origin), background: tokens.store, color: tokens.storeText }" title="A loja" data-map-store>
      <NuxtIcon name="i-lucide-store" class="size-4" />
    </span>

    <!-- corrida chamada: octógono branco de borda contínua; entregue fica sólido, com o visto -->
    <template v-for="r in live" :key="`ls${r.number}`">
      <span v-for="(s, k) in r.stops" :key="s.ref" :class="MARKER" :style="at(s, s.ref)">
        <NuxtButton color="neutral" variant="ghost" class="p-1" :aria-label="`Corrida ${rideLetter(r.number)}, parada ${k + 1}, pedido ${s.code}${s.done ? ', entregue' : ''}`" @click="emit('open', r.number)">
          <span class="relative grid size-9 place-items-center op-label font-bold tabular-nums" :style="{ color: s.done ? rideColor(r.number - 1).fg : rideColor(r.number - 1).ink }">
            <svg class="absolute inset-0 size-full drop-shadow-sm" viewBox="0 0 36 36" aria-hidden="true">
              <polygon v-if="s.done" :points="OCTAGON" :fill="rideColor(r.number - 1).bg" stroke-width="4" stroke-linejoin="round" :stroke="dark ? lineOutline(tokens, rideColor(r.number - 1)) : rideColor(r.number - 1).bg" />
              <polygon v-else :points="OCTAGON" fill="#fff" stroke-width="4" stroke-linejoin="round" :stroke="rideColor(r.number - 1).bg" :stroke-opacity="liveAlpha" />
            </svg>
            <span class="relative"><NuxtIcon v-if="s.done" name="i-lucide-check" class="size-3.5" /><template v-else>{{ k + 1 }}</template></span>
            <span class="absolute -top-1.5 -right-1.5 grid size-4.5 place-items-center rounded-[4px] op-micro leading-none font-bold ring-1 ring-white" :style="{ background: rideColor(r.number - 1).bg, color: rideColor(r.number - 1).fg }" aria-hidden="true" data-stop-letter>{{ rideLetter(r.number) }}</span>
          </span>
        </NuxtButton>
      </span>
    </template>

    <!-- editando: octógono de borda pontilhada na cor da corrida -->
    <template v-for="r in building" :key="`bs${r.number}`">
      <span v-for="(s, k) in r.stops" :key="s.ref" :class="[MARKER, 'z-10']" :style="at(s, s.ref)">
        <NuxtButton color="neutral" variant="ghost" class="p-1" :aria-label="`Pedido ${s.code}, parada ${k + 1} da corrida ${rideLetter(r.number)}`" @click="emit('toggle', s.ref)">
          <span class="relative grid size-9 place-items-center op-label font-bold tabular-nums transition hover:scale-110" :style="{ color: rideColor(r.number - 1).ink }">
            <svg class="absolute inset-0 size-full drop-shadow-sm" viewBox="0 0 36 36" aria-hidden="true">
              <defs><pattern :id="`stripe-b${r.number}`" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="4" height="4" fill="#fff" /><rect width="1.5" height="4" :fill="rideColor(r.number - 1).bg" /></pattern></defs>
              <polygon :points="OCTAGON" :fill="`url(#stripe-b${r.number})`" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="0.1 6" :stroke="rideColor(r.number - 1).bg" />
            </svg>
            <span class="relative">{{ k + 1 }}</span>
            <span class="absolute -top-1.5 -right-1.5 grid size-4.5 place-items-center rounded-[4px] op-micro leading-none font-bold ring-1 ring-white" :style="{ background: rideColor(r.number - 1).bg, color: rideColor(r.number - 1).fg }" aria-hidden="true" data-stop-letter>{{ rideLetter(r.number) }}</span>
          </span>
        </NuxtButton>
      </span>
    </template>

    <!-- aguardando: redondos, preto e branco, com o código (parada de corrida é octógono na cor) -->
    <span v-for="o in waiting" :key="o.ref" :class="[MARKER, 'z-10']" :style="at(o, o.ref)">
      <NuxtButton color="neutral" variant="ghost" class="p-1" :aria-label="`Pedido ${o.code}, ${o.place}${o.preparing ? ', em preparo' : ''}`" @click="emit('toggle', o.ref)">
        <span class="relative grid size-9 place-items-center rounded-full border-2 border-black bg-white op-micro font-semibold tabular-nums text-black shadow-md transition hover:scale-110">
          {{ o.code }}
          <span v-if="o.preparing" class="absolute -right-1 -bottom-1 grid size-4 place-items-center rounded-full bg-white ring-1 ring-black/20" :style="{ color: PIN_TEXT }" title="Em preparo"><NuxtIcon name="i-lucide-chef-hat" class="size-2.5" /></span>
        </span>
      </NuxtButton>
    </span>

    <!-- o entregador: o único cheio de cor -->
    <template v-for="r in live" :key="`c${r.number}`">
      <span v-if="r.courier" :class="[MARKER, 'z-20']" :style="at(r.courier, `courier:${r.number}`)" :data-map-courier="rideLetter(r.number)" :data-map-courier-stale="courierAge(r)?.stale ? '' : undefined">
        <NuxtButton color="neutral" variant="ghost" class="p-1.5" :aria-label="[`Entregador da corrida ${rideLetter(r.number)}`, courierAge(r)?.sentence].filter(Boolean).join('. ')" @click="emit('open', r.number)">
          <span class="flex items-center gap-1 rounded-full py-1 pr-2 pl-1 shadow-lg ring-2 ring-white transition hover:scale-105" :class="courierAge(r)?.stale ? 'opacity-45 grayscale-[35%]' : ''" :style="{ background: rideColor(r.number - 1).bg, color: rideColor(r.number - 1).fg }">
            <span class="grid size-6 place-items-center rounded-full bg-white/20"><NuxtIcon name="i-lucide-bike" class="size-4" /></span>
            <span class="op-label font-bold">{{ rideLetter(r.number) }}</span>
          </span>
        </NuxtButton>
        <!-- Posição que não é de agora: a moto diz desde quando estava ali (sem amarelo: não há o que fazer). -->
        <span v-if="courierAge(r)?.mapLabel" :ref="keepInside" class="pointer-events-none absolute top-full left-1/2 -mt-1 -translate-x-1/2 whitespace-nowrap rounded px-1.5 py-0.5 op-micro font-medium shadow-sm" :style="{ background: tokens.chip, color: tokens.text }" aria-hidden="true" data-map-courier-age>{{ courierAge(r)?.mapLabel }}</span>
      </span>
    </template>

    </div>
    </Teleport>

    <!-- legenda pela FORMA, nunca pela cor: a cor é sempre a da corrida -->
    <div v-if="!bare && legendCollapsible && !legendOpen" class="absolute top-3 left-3 z-30 rounded-md shadow-sm">
      <NuxtButton color="neutral" variant="outline" icon="i-lucide-info" label="Legenda" class="min-h-11" aria-expanded="false" data-map-legend-toggle @click="legendOpen = true" />
    </div>
    <div v-if="!bare && (!legendCollapsible || legendOpen)" :ref="observeLegend" class="absolute inset-x-3 top-3 mx-auto flex w-fit flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-md px-2.5 py-1.5 op-micro shadow-sm" :class="legendCollapsible ? 'z-40 pr-1' : ''" :style="{ background: tokens.chip, color: tokens.text }" data-map-legend>
      <span class="flex items-center gap-1"><span class="size-3.5 rounded-full border-2 border-black bg-white" />Aguardando</span>
      <span class="flex items-center gap-1"><svg width="16" height="6" aria-hidden="true"><path d="M2 3H15" :stroke="tokens.neutral" stroke-width="3" stroke-dasharray="0.1 5" stroke-linecap="round" /></svg><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><defs><pattern id="legend-stripe" width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="3" height="3" fill="#fff" /><rect width="1.1" height="3" :fill="tokens.neutral" /></pattern></defs><polygon points="12.2,9.1 9.1,12.2 4.9,12.2 1.8,9.1 1.8,4.9 4.9,1.8 9.1,1.8 12.2,4.9" fill="url(#legend-stripe)" :stroke="tokens.neutral" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="0.1 3.2" /></svg>Editando</span>
      <span class="flex items-center gap-1"><svg width="16" height="6" aria-hidden="true"><path d="M1 3H15" :stroke="tokens.neutral" stroke-width="3" stroke-linecap="round" /></svg><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><polygon points="12.2,9.1 9.1,12.2 4.9,12.2 1.8,9.1 1.8,4.9 4.9,1.8 9.1,1.8 12.2,4.9" fill="#fff" :stroke="tokens.neutral" stroke-width="2.5" stroke-linejoin="round" /></svg>Corrida</span>
      <span class="flex items-center gap-1"><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><polygon points="12.2,9.1 9.1,12.2 4.9,12.2 1.8,9.1 1.8,4.9 4.9,1.8 9.1,1.8 12.2,4.9" :fill="tokens.neutral" :stroke="tokens.neutral" stroke-width="2.5" stroke-linejoin="round" /></svg>Entregue</span>
      <span class="flex items-center gap-1"><span class="grid h-4 w-6 place-items-center rounded-full" :style="{ background: tokens.neutral, color: tokens.chip }"><NuxtIcon name="i-lucide-bike" class="size-3" /></span>Entregador</span>
      <span v-if="ghosts.length" class="flex items-center gap-1" data-map-legend-suggestion><svg width="22" height="6" aria-hidden="true"><path d="M2 3H20" :stroke="tokens.neutral" stroke-width="3" stroke-dasharray="7 4" stroke-linecap="round" /></svg>Sugestão</span>
      <NuxtButton v-if="legendCollapsible" color="neutral" variant="ghost" icon="i-lucide-x" class="min-h-11 min-w-11 justify-center" aria-label="Fechar a legenda" aria-expanded="true" data-map-legend-close @click="legendOpen = false" />
    </div>

    <!-- Depois do gesto do operador o mapa fica onde ele deixou; isto devolve o quadro inteiro. -->
    <div v-if="userMoved && real" class="absolute bottom-3 left-3">
      <NuxtButton color="neutral" variant="outline" icon="i-lucide-scan" label="Ver tudo" data-map-show-all @click="showAll" />
    </div>
  </div>
</template>
