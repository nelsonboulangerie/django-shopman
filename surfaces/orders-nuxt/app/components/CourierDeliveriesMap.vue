<script setup lang="ts">
// O mapa da página Entregas: tudo o que está fora da loja ou a
// caminho dela, num desenho só.
//
// Os desenhos são os da escolha do dono (21/11; ver `presentation/mapGlyphs`): a loja é
// o ícone de loja, a parada é um PACOTE (saco de pão: picote em cima, base reta embaixo,
// pousada no ponto) com o código do pedido no corpo, o entregador é a própria moto. Moto
// e pacote são inteiros na cor da rota; a loja é neutra. O traço de todo ícone tem a
// espessura da linha da rota, e cada pino e cada linha levam um contorno na cor do tema.
// Nada tem transparência.
//  · CHAMADA (na rua): pacote cheio na cor; rota contínua. A parada já entregue troca o
//    código pelo visto.
//  · EDITANDO: pacote de papel branco, borda tracejada na cor; rota PONTILHADA.
//  · AGUARDANDO: o pedido sem corrida, REDONDO, preto e branco, com o código. A forma
//    e a falta de cor separam o que espera do que já tem corrida (dono, 15 e 16/11).
//    Tocar põe na ativa.
//
// O fundo é o Google Maps de verdade (dono, 14/11: "Pq não mostra um mapa de
// verdade?"), com a chave pública do navegador. As camadas acima são as nossas,
// presas ao mapa por um OverlayView: arrastar e dar zoom levam tudo junto. Sem chave,
// ou se o Google recusar, o desenho próprio (trama de ruas) fica no lugar.
//
// Legível e tocável (revisão das Entregas, 16/11/2026, F7a): as cores
// do mapa são fixas por tema (acompanham o claro e o escuro, dono 17/11); todo alvo tem 44 px; pinos no
// mesmo ponto se abrem em círculo; o enquadramento não corre atrás da moto e, depois
// que o operador mexe no mapa, "Ver tudo" devolve o quadro inteiro. Loja sem
// coordenada não se desenha (antes ia parar na casa de um cliente).
import { rideColor } from "~/presentation/ridePalette";
import { PIN_TEXT, fitKey, googleMapStyles, mapTokens, spreadOverlaps } from "~/presentation/deliveriesMap";
import { GLYPH_INK, GLYPH_PAPER, HALO_WIDTH, ICON_VIEWBOX, MOTO_PATHS, PACKAGE_PATH, PACKAGE_TEXT_Y, PACKAGE_VIEWBOX, ROUTE_WIDTH, STORE_AWNING, STORE_PATH, STORE_WALL, routeColor, textOn, themeHalo } from "~/presentation/mapGlyphs";
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
const halo = computed(() => themeHalo(dark.value));
/** A cor da rota da corrida `n` (1 = A), e a do texto sobre o pacote cheio dela. */
const route = (n: number) => routeColor(dark.value, rideColor(n - 1));
const routeText = (n: number) => textOn(route(n));

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
  // Folga fixa em pixels: o pacote fica todo ACIMA do ponto dele (a base pousa no ponto),
  // então a folga de cima cobre a altura do pacote.
  const b = bounds.value, side = 24, top = topBand.value + 52, bottom = 24;
  return {
    x: side + ((p.longitude - b.minLng) / (b.maxLng - b.minLng)) * (size.value.w - 2 * side),
    y: top + (1 - (p.latitude - b.minLat) / (b.maxLat - b.minLat)) * (size.value.h - top - bottom),
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
  // O pacote fica todo acima do ponto dele: a folga de cima cobre a altura do pacote.
  map.fitBounds(area, props.bare ? { top: 56, right: 32, bottom: 28, left: 32 } : { top: 64 + topBand.value, right: 56, bottom: 56, left: 56 });
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
// O pacote fica todo ACIMA do ponto (a base pousa nele): a caixa que se compara é a do
// desenho, com o contorno, e não um quadrado centrado no ponto.
const PACKAGE_BOX = { w: 44, h: 50, lift: 23 };
const packageBox = (s: LatLng & { ref: string }) => {
  const q = px(s);
  return { key: s.ref, x: q.x, y: q.y - PACKAGE_BOX.lift, w: PACKAGE_BOX.w, h: PACKAGE_BOX.h };
};
const offsets = computed(() =>
  spreadOverlaps([
    ...props.waiting.map((o) => ({ key: o.ref, ...px(o) })),
    ...props.building.flatMap((r) => r.stops.map(packageBox)),
    ...props.live.flatMap((r) => [
      ...r.stops.map(packageBox),
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
/** O pacote pousa a base no ponto: âncora no centro da base, não no meio do desenho. */
const PACKAGE_MARKER = "absolute -translate-x-1/2 -translate-y-full hover:z-30 focus-within:z-30";

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
  // O rótulo que cairia sobre a loja começa depois da borda dela (a loja tem 48 px; o
  // rótulo fica 20 px abaixo do pino mais baixo do bairro e tem ~22 px de altura).
  const store = props.origin ? px(props.origin) : null;
  return [...groups.entries()].map(([place, g]) => {
    const x = g.x / g.n, top = g.y + 20, half = place.length * 3.4 + 12;
    const hits = store && Math.abs(x - store.x) < half + 24 && top < store.y + 24 && top + 22 > store.y - 24;
    return hits ? { place, x: store.x + 24 + 6, y: g.y, start: true } : { place, x, y: g.y, start: false };
  });
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
        :data-map-suggestion="g.key"
      />
      <!-- o contorno na cor do tema, por baixo: separa a linha do mapa -->
      <path
        v-for="l in lines"
        :key="`o${l.live ? 'l' : 'b'}${l.id}`"
        :d="l.d"
        fill="none"
        :stroke="halo"
        :stroke-width="HALO_WIDTH"
        stroke-linecap="round"
        stroke-linejoin="round"
        :stroke-dasharray="l.live ? undefined : '0.1 8'"
        data-line-outline
      />
      <path
        v-for="l in lines"
        :key="`${l.live ? 'l' : 'b'}${l.id}`"
        :d="l.d"
        fill="none"
        :stroke="route(l.id)"
        :stroke-width="ROUTE_WIDTH"
        stroke-linecap="round"
        stroke-linejoin="round"
        :stroke-dasharray="l.live ? undefined : '0.1 8'"
      />
    </svg>

    <!-- Cada alvo de toque: um marcador de posição, o botão do kit (sem estilo
         próprio) e, dentro dele, o desenho na cor da corrida. -->
    <span
      v-for="label in places"
      :key="label.place"
      class="absolute translate-y-5"
      :class="label.start ? '' : '-translate-x-1/2'"
      :style="{ left: `${label.x}px`, top: `${label.y}px` }"
      :data-map-place-after-store="label.start ? '' : undefined"
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

    <!-- a loja: o ícone de loja em traço escuro, parede e toldo brancos; a maior do mapa -->
    <span v-if="origin" class="absolute z-10 size-12 -translate-x-1/2 -translate-y-1/2" :style="at(origin)" title="A loja" data-map-store>
      <svg class="size-full overflow-visible" :viewBox="ICON_VIEWBOX" aria-hidden="true">
        <path :d="STORE_PATH" fill="none" :stroke="halo" :stroke-width="HALO_WIDTH" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
        <rect v-bind="STORE_WALL" :fill="GLYPH_PAPER" />
        <path :d="STORE_AWNING" :fill="GLYPH_PAPER" />
        <path :d="STORE_PATH" fill="none" :stroke="GLYPH_INK" :stroke-width="ROUTE_WIDTH" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
      </svg>
    </span>

    <!-- Posição que não é de agora: a moto diz desde quando estava ali (sem amarelo: não há o
         que fazer). Fica numa camada ABAIXO das paradas, embaixo da moto: é só leitura e nunca cobre um pacote. -->
    <template v-for="r in live" :key="`ca${r.number}`">
      <span v-if="r.courier && courierAge(r)?.mapLabel" :class="MARKER" class="pointer-events-none" :style="at(r.courier, `courier:${r.number}`)" aria-hidden="true">
        <span class="block size-11" />
        <span :ref="keepInside" class="absolute top-full left-1/2 -mt-1 -translate-x-1/2 whitespace-nowrap rounded px-1.5 py-0.5 op-micro font-medium shadow-sm" :style="{ background: tokens.chip, color: tokens.text }" data-map-courier-age>{{ courierAge(r)?.mapLabel }}</span>
      </span>
    </template>

    <!-- corrida chamada: pacote cheio na cor da rota, com o código; entregue troca o código
         pelo visto. A base reta pousa no ponto do mapa (âncora no centro da base). -->
    <template v-for="r in live" :key="`ls${r.number}`">
      <span v-for="(s, k) in r.stops" :key="s.ref" :class="PACKAGE_MARKER" :style="at(s, s.ref)">
        <NuxtButton color="neutral" variant="ghost" class="min-h-11 min-w-11 items-end justify-center px-1 pt-1 pb-0" :aria-label="`Corrida ${rideLetter(r.number)}, parada ${k + 1}, pedido ${s.code}${s.done ? ', entregue' : ''}`" @click="emit('open', r.number)">
          <span class="relative block h-[42px] w-[34px]" data-map-stop>
            <svg class="absolute inset-0 size-full overflow-visible" :viewBox="PACKAGE_VIEWBOX" aria-hidden="true">
              <path :d="PACKAGE_PATH" fill="none" :stroke="halo" :stroke-width="HALO_WIDTH" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
              <path :d="PACKAGE_PATH" :fill="route(r.number)" :stroke="route(r.number)" :stroke-width="ROUTE_WIDTH" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
              <text x="17" :y="s.done ? PACKAGE_TEXT_Y - 5 : PACKAGE_TEXT_Y" text-anchor="middle" dominant-baseline="central" font-weight="800" font-size="11" :fill="routeText(r.number)" data-map-stop-code>{{ s.code }}</text>
              <!-- entregue: o visto pequeno abaixo do código, dentro do pacote -->
              <path v-if="s.done" d="M12.5 31 l3 3 l6 -6.5" fill="none" :stroke="routeText(r.number)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" data-map-stop-done />
            </svg>
          </span>
        </NuxtButton>
      </span>
    </template>

    <!-- editando: pacote de papel branco, borda tracejada na cor da rota -->
    <template v-for="r in building" :key="`bs${r.number}`">
      <span v-for="(s, k) in r.stops" :key="s.ref" :class="[PACKAGE_MARKER, 'z-10']" :style="at(s, s.ref)">
        <NuxtButton color="neutral" variant="ghost" class="min-h-11 min-w-11 items-end justify-center px-1 pt-1 pb-0" :aria-label="`Pedido ${s.code}, parada ${k + 1} da corrida ${rideLetter(r.number)}`" @click="emit('toggle', s.ref)">
          <span class="relative block h-[42px] w-[34px] transition hover:scale-110" data-map-stop data-map-stop-editing>
            <svg class="absolute inset-0 size-full overflow-visible" :viewBox="PACKAGE_VIEWBOX" aria-hidden="true">
              <path :d="PACKAGE_PATH" fill="none" :stroke="halo" :stroke-width="HALO_WIDTH" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
              <path :d="PACKAGE_PATH" :fill="GLYPH_PAPER" :stroke="route(r.number)" :stroke-width="ROUTE_WIDTH" stroke-linejoin="round" stroke-dasharray="6 4" vector-effect="non-scaling-stroke" />
              <text x="17" :y="PACKAGE_TEXT_Y" text-anchor="middle" dominant-baseline="central" font-weight="800" font-size="11" :fill="GLYPH_INK" data-map-stop-code>{{ s.code }}</text>
            </svg>
          </span>
        </NuxtButton>
      </span>
    </template>

    <!-- aguardando: redondos, preto e branco, com o código (parada de corrida é pacote) -->
    <span v-for="o in waiting" :key="o.ref" :class="[MARKER, 'z-10']" :style="at(o, o.ref)">
      <NuxtButton color="neutral" variant="ghost" class="p-1" :aria-label="`Pedido ${o.code}, ${o.place}${o.preparing ? ', em preparo' : ''}`" @click="emit('toggle', o.ref)">
        <span class="relative grid size-9 place-items-center rounded-full border-2 border-black bg-white op-micro font-semibold tabular-nums text-black shadow-md transition hover:scale-110">
          {{ o.code }}
          <span v-if="o.preparing" class="absolute -right-1 -bottom-1 grid size-4 place-items-center rounded-full bg-white ring-1 ring-black/20" :style="{ color: PIN_TEXT }" title="Em preparo"><NuxtIcon name="i-lucide-chef-hat" class="size-2.5" /></span>
        </span>
      </NuxtButton>
    </span>

    <!-- o entregador: a própria moto, em traço na cor da rota; a posição antiga encolhe e
         ganha um anel tracejado (sem transparência) -->
    <template v-for="r in live" :key="`c${r.number}`">
      <span v-if="r.courier" :class="[MARKER, 'z-20']" :style="at(r.courier, `courier:${r.number}`)" :data-map-courier="rideLetter(r.number)" :data-map-courier-stale="courierAge(r)?.stale ? '' : undefined">
        <NuxtButton color="neutral" variant="ghost" class="p-1.5" :aria-label="[`Entregador da corrida ${rideLetter(r.number)}`, courierAge(r)?.sentence].filter(Boolean).join('. ')" @click="emit('open', r.number)">
          <span class="relative block transition hover:scale-105" :class="courierAge(r)?.stale ? 'size-8' : 'size-10'">
            <svg class="size-full overflow-visible" :viewBox="ICON_VIEWBOX" aria-hidden="true">
              <circle v-if="courierAge(r)?.stale" cx="12" cy="12" r="15" fill="none" :stroke="tokens.text" stroke-width="1.5" stroke-dasharray="3 2.5" vector-effect="non-scaling-stroke" />
              <path v-for="d in MOTO_PATHS" :key="`h${d}`" :d="d" fill="none" :stroke="halo" :stroke-width="HALO_WIDTH" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
              <path v-for="d in MOTO_PATHS" :key="d" :d="d" fill="none" :stroke="route(r.number)" :stroke-width="ROUTE_WIDTH" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
            </svg>
          </span>
        </NuxtButton>
      </span>
    </template>

    </div>
    </Teleport>

    <!-- legenda pela FORMA, nunca pela cor: a cor é sempre a da corrida -->
    <div v-if="!bare && legendCollapsible && !legendOpen" class="absolute top-3 left-3 z-30 rounded-md shadow-sm">
      <NuxtButton color="neutral" variant="outline" icon="i-lucide-info" label="Legenda" class="min-h-11" aria-expanded="false" data-map-legend-toggle @click="legendOpen = true" />
    </div>
    <div v-if="!bare && (!legendCollapsible || legendOpen)" :ref="observeLegend" class="absolute inset-x-3 top-3 mx-auto flex w-fit flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-md px-2.5 py-1.5 op-micro shadow-sm" :class="legendCollapsible ? 'z-40 pr-1' : ''" :style="{ background: tokens.chip, color: tokens.text }" data-map-legend>
      <span class="flex items-center gap-1"><svg width="16" height="16" :viewBox="ICON_VIEWBOX" class="overflow-visible" aria-hidden="true"><rect v-bind="STORE_WALL" :fill="GLYPH_PAPER" /><path :d="STORE_AWNING" :fill="GLYPH_PAPER" /><path :d="STORE_PATH" fill="none" :stroke="tokens.text" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" /></svg>Loja</span>
      <span class="flex items-center gap-1"><span class="size-3.5 rounded-full border-2 border-black bg-white" />Aguardando</span>
      <span class="flex items-center gap-1"><svg width="16" height="6" aria-hidden="true"><path d="M2 3H15" :stroke="tokens.neutral" stroke-width="3" stroke-dasharray="0.1 5" stroke-linecap="round" /></svg><svg width="13" height="16" :viewBox="PACKAGE_VIEWBOX" class="overflow-visible" aria-hidden="true"><path :d="PACKAGE_PATH" :fill="GLYPH_PAPER" :stroke="tokens.text" stroke-width="1.6" stroke-linejoin="round" stroke-dasharray="3 2" vector-effect="non-scaling-stroke" /></svg>Editando</span>
      <span class="flex items-center gap-1"><svg width="16" height="6" aria-hidden="true"><path d="M1 3H15" :stroke="tokens.neutral" stroke-width="3" stroke-linecap="round" /></svg><svg width="13" height="16" :viewBox="PACKAGE_VIEWBOX" class="overflow-visible" aria-hidden="true"><path :d="PACKAGE_PATH" :fill="tokens.text" :stroke="tokens.text" stroke-width="1.6" stroke-linejoin="round" vector-effect="non-scaling-stroke" /></svg>Corrida</span>
      <span class="flex items-center gap-1"><svg width="13" height="16" :viewBox="PACKAGE_VIEWBOX" class="overflow-visible" aria-hidden="true"><path :d="PACKAGE_PATH" :fill="tokens.text" :stroke="tokens.text" stroke-width="1.6" stroke-linejoin="round" vector-effect="non-scaling-stroke" /><path d="M10 24 l5 5 l9 -10" fill="none" :stroke="tokens.chip" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" /></svg>Entregue</span>
      <span class="flex items-center gap-1"><svg width="18" height="18" :viewBox="ICON_VIEWBOX" aria-hidden="true"><path v-for="d in MOTO_PATHS" :key="d" :d="d" fill="none" :stroke="tokens.text" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" /></svg>Entregador</span>
      <span v-if="ghosts.length" class="flex items-center gap-1" data-map-legend-suggestion><svg width="22" height="6" aria-hidden="true"><path d="M2 3H20" :stroke="tokens.neutral" stroke-width="3" stroke-dasharray="7 4" stroke-linecap="round" /></svg>Sugestão</span>
      <NuxtButton v-if="legendCollapsible" color="neutral" variant="ghost" icon="i-lucide-x" class="min-h-11 min-w-11 justify-center" aria-label="Fechar a legenda" aria-expanded="true" data-map-legend-close @click="legendOpen = false" />
    </div>

    <!-- Depois do gesto do operador o mapa fica onde ele deixou; isto devolve o quadro inteiro. -->
    <div v-if="userMoved && real" class="absolute bottom-3 left-3">
      <NuxtButton color="neutral" variant="outline" icon="i-lucide-scan" label="Ver tudo" data-map-show-all @click="showAll" />
    </div>
  </div>
</template>
