<script setup lang="ts">
// PRÉVIA (14/11) — o planejador de corridas: montar UMA OU VÁRIAS corridas de uma
// vez, no mapa e na lista, e chamar todas num toque.
//
// A dinâmica, do jeito que o operador pensa:
//  · há sempre uma corrida "na mão" (a ativa, com a cor dela);
//  · tocar num ponto (mapa) ou numa linha (lista) põe o pedido na corrida ativa;
//    tocar de novo tira. Tocar num pedido que está em OUTRA corrida o traz para a ativa;
//  · o bairro sugerido ("Juntos por bairro") enche a corrida ativa num toque;
//  · "Nova corrida" abre a próxima cor; o que sobrou continua no mapa;
//  · "Chamar N corridas" chama todas; o modal fecha e cada corrida vira um cartão
//    no Saída, que acompanha a corrida até o entregador voltar.
export interface PlannerOrder {
  ref: string;
  code: string;
  customer: string;
  place: string;
  stage: "Pronto" | "Em preparo";
  latitude: number;
  longitude: number;
  asks?: "troco" | "maquininha" | "";
}
const props = defineProps<{
  orders: PlannerOrder[];
  origin: { latitude: number; longitude: number };
  initial?: string[][];
  initialActive?: number;
}>();

const MAX = 4;
const COLORS = [
  { name: "bronze", dot: "#8b6a2f", soft: "rgba(139,106,47,.18)" },
  { name: "azul", dot: "#2f6f9f", soft: "rgba(47,111,159,.18)" },
  { name: "verde", dot: "#3f7f4f", soft: "rgba(63,127,79,.18)" },
  { name: "vinho", dot: "#8f3a4a", soft: "rgba(143,58,74,.18)" },
];
const rides = ref<string[][]>(props.initial?.map((r) => [...r]) ?? [[]]);
const active = ref(props.initialActive ?? 0);

const rideOf = (ref: string) => rides.value.findIndex((ride) => ride.includes(ref));
function toggle(ref: string) {
  const at = rideOf(ref);
  const mine = rides.value[active.value]!;
  if (at === active.value) {
    rides.value[active.value] = mine.filter((r) => r !== ref);
    return;
  }
  if (mine.length >= MAX) return;
  if (at >= 0) rides.value[at] = rides.value[at]!.filter((r) => r !== ref);
  rides.value[active.value] = [...mine, ref];
}
function fillWithPlace(place: string) {
  const refs = props.orders.filter((o) => o.place === place && (rideOf(o.ref) < 0 || rideOf(o.ref) === active.value)).map((o) => o.ref);
  rides.value[active.value] = refs.slice(0, MAX);
}
function newRide() {
  if (rides.value.length >= COLORS.length) return;
  rides.value.push([]);
  active.value = rides.value.length - 1;
}
function dropRide(index: number) {
  rides.value.splice(index, 1);
  if (!rides.value.length) rides.value.push([]);
  active.value = Math.min(active.value, rides.value.length - 1);
}
const ready = computed(() => rides.value.filter((ride) => ride.length >= 1));
const free = computed(() => props.orders.filter((o) => rideOf(o.ref) < 0));
const byPlace = computed(() => {
  const map = new Map<string, PlannerOrder[]>();
  for (const o of props.orders) map.set(o.place, [...(map.get(o.place) || []), o]);
  return [...map.entries()].map(([place, rows]) => ({ place, rows }));
});
const suggestions = computed(() =>
  byPlace.value
    .map(({ place, rows }) => ({ place, n: rows.filter((o) => rideOf(o.ref) < 0 || rideOf(o.ref) === active.value).length }))
    .filter((s) => s.n >= 2),
);
const order = (ref: string) => props.orders.find((o) => o.ref === ref)!;

// ── mapa ─────────────────────────────────────────────────────────────────────
const bounds = computed(() => {
  const all = [...props.orders, props.origin];
  const lats = all.map((p) => p.latitude), lngs = all.map((p) => p.longitude);
  const dLat = Math.max(...lats) - Math.min(...lats), dLng = Math.max(...lngs) - Math.min(...lngs);
  return { minLat: Math.min(...lats) - dLat * 0.14, maxLat: Math.max(...lats) + dLat * 0.14, minLng: Math.min(...lngs) - dLng * 0.12, maxLng: Math.max(...lngs) + dLng * 0.12 };
});
function xy(p: { latitude: number; longitude: number }) {
  const b = bounds.value;
  return { x: ((p.longitude - b.minLng) / (b.maxLng - b.minLng)) * 100, y: (1 - (p.latitude - b.minLat) / (b.maxLat - b.minLat)) * 100 };
}
const placeLabels = computed(() =>
  byPlace.value.map(({ place, rows }) => {
    const pts = rows.map(xy);
    return { place, x: pts.reduce((s, p) => s + p.x, 0) / pts.length, y: Math.max(...pts.map((p) => p.y)) };
  }),
);
const paths = computed(() =>
  rides.value.map((ride, i) => ({
    i,
    d: [props.origin, ...ride.map(order)].map(xy).map((p, k) => `${k ? "L" : "M"}${p.x} ${p.y}`).join(" "),
  })).filter((p) => rides.value[p.i]!.length),
);
const callLabel = computed(() =>
  ready.value.length === 1 ? `Chamar a corrida (${ready.value[0]!.length})` : `Chamar ${ready.value.length} corridas`,
);
</script>

<template>
  <div class="grid h-[min(78dvh,46rem)] min-h-0 grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]" data-ride-planner>
    <!-- o mapa: a loja, os pedidos, as corridas desenhadas por cor -->
    <div class="relative min-h-0 border-r border-default">
      <div class="absolute inset-0 overflow-hidden bg-[#f3ede3]">
        <svg class="absolute inset-0 size-full" aria-hidden="true">
          <defs>
            <pattern id="ride-streets" width="46" height="46" patternUnits="userSpaceOnUse" patternTransform="rotate(-12)">
              <path d="M46 0H0V46" fill="none" stroke="#fff" stroke-width="5" />
              <path d="M46 0H0V46" fill="none" stroke="#e4dccd" stroke-width="1" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#ride-streets)" />
        </svg>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="absolute inset-0 size-full" aria-hidden="true">
          <path v-for="p in paths" :key="p.i" :d="p.d" fill="none" :stroke="COLORS[p.i]!.dot" vector-effect="non-scaling-stroke" style="stroke-width: 3px" :stroke-dasharray="p.i === active ? '0' : '6 5'" stroke-linecap="round" stroke-linejoin="round" :opacity="p.i === active ? 0.95 : 0.55" />
        </svg>
        <button
          v-for="label in placeLabels"
          :key="label.place"
          type="button"
          class="absolute -translate-x-1/2 translate-y-5 whitespace-nowrap rounded-full bg-white/85 px-2 py-0.5 op-micro font-semibold text-toned shadow-sm transition hover:bg-white hover:text-highlighted"
          :style="{ left: `${label.x}%`, top: `${label.y}%` }"
          :title="`Pôr ${label.place} na corrida ${active + 1}`"
          @click="fillWithPlace(label.place)"
        >{{ label.place }}</button>
        <span class="absolute grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-inverted text-inverted shadow-lg ring-4 ring-white" :style="{ left: `${xy(origin).x}%`, top: `${xy(origin).y}%` }" title="A loja">
          <NuxtIcon name="i-lucide-store" class="size-4" />
        </span>
        <button
          v-for="o in orders"
          :key="o.ref"
          type="button"
          class="absolute grid -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full font-semibold tabular-nums shadow-md transition hover:scale-110"
          :class="rideOf(o.ref) >= 0 ? 'size-9 text-white ring-4' : 'size-8 border-2 bg-white op-micro'"
          :style="rideOf(o.ref) >= 0
            ? { left: `${xy(o).x}%`, top: `${xy(o).y}%`, background: COLORS[rideOf(o.ref)]!.dot, '--tw-ring-color': COLORS[rideOf(o.ref)]!.soft }
            : { left: `${xy(o).x}%`, top: `${xy(o).y}%`, borderColor: '#b9a888', color: '#5b4a2c' }"
          :aria-label="`Pedido ${o.code}, ${o.place}`"
          @click="toggle(o.ref)"
        >
          {{ rideOf(o.ref) >= 0 ? rides[rideOf(o.ref)]!.indexOf(o.ref) + 1 : o.code }}
          <span v-if="o.stage === 'Em preparo'" class="absolute -right-1 -bottom-1 grid size-4 place-items-center rounded-full bg-white text-[9px] text-toned ring-1 ring-default" title="Em preparo"><NuxtIcon name="i-lucide-chef-hat" class="size-2.5" /></span>
        </button>
        <p class="absolute bottom-3 left-3 rounded-md bg-white/90 px-2.5 py-1.5 op-micro text-toned shadow-sm">
          Toque no pedido para pôr na corrida <span class="font-semibold" :style="{ color: COLORS[active]!.dot }">{{ active + 1 }}</span>. Toque no bairro para pôr todos.
        </p>
      </div>
    </div>

    <!-- as corridas: a ativa aberta, as outras resumidas; o que sobrou embaixo -->
    <div class="flex min-h-0 flex-col">
      <div class="min-h-0 flex-1 overflow-y-auto p-4">
        <div v-if="suggestions.length" class="mb-4 flex flex-col gap-2">
          <p class="op-micro font-semibold text-muted">Juntos por bairro</p>
          <div class="flex flex-wrap gap-1.5">
            <NuxtButton v-for="s in suggestions" :key="s.place" size="sm" color="neutral" variant="outline" icon="i-lucide-map-pin" :label="`${s.place} · ${s.n}`" @click="fillWithPlace(s.place)" />
          </div>
        </div>

        <div class="flex flex-col gap-2">
          <section
            v-for="(ride, i) in rides"
            :key="i"
            class="rounded-xl border transition"
            :style="i === active ? { borderColor: COLORS[i]!.dot, boxShadow: `0 0 0 3px ${COLORS[i]!.soft}` } : {}"
            :class="i === active ? 'bg-default' : 'border-default bg-elevated/50'"
          >
            <button type="button" class="flex w-full items-center gap-2 px-3 py-2.5 text-left" @click="active = i">
              <span class="size-3 shrink-0 rounded-full" :style="{ background: COLORS[i]!.dot }" />
              <span class="op-label font-semibold text-highlighted">Corrida {{ i + 1 }}</span>
              <span class="op-micro tabular-nums text-muted">{{ ride.length }} de {{ MAX }}</span>
              <span v-if="i !== active && ride.length" class="ml-1 min-w-0 flex-1 truncate op-micro text-muted">{{ ride.map((r) => order(r).code).join(" → ") }}</span>
              <span v-else class="flex-1" />
              <NuxtButton v-if="rides.length > 1" icon="i-lucide-trash-2" size="xs" color="neutral" variant="ghost" square :aria-label="`Desfazer a corrida ${i + 1}`" @click.stop="dropRide(i)" />
            </button>
            <ol v-if="i === active" class="flex flex-col gap-1 px-3 pb-3">
              <li v-if="!ride.length" class="rounded-lg border border-dashed border-default px-3 py-3 text-center op-body text-muted">
                Toque nos pedidos no mapa ou na lista.
              </li>
              <li v-for="(ref, k) in ride" :key="ref" class="flex items-center gap-2.5 rounded-lg bg-elevated/60 px-2 py-1.5">
                <span class="grid size-6 shrink-0 place-items-center rounded-full op-micro font-semibold text-white" :style="{ background: COLORS[i]!.dot }">{{ k + 1 }}</span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate op-body font-medium text-highlighted">{{ order(ref).code }} · {{ order(ref).customer }}</span>
                  <span class="block truncate op-micro text-muted">{{ order(ref).place }} · {{ order(ref).stage }}<template v-if="order(ref).asks"> · leva {{ order(ref).asks }}</template></span>
                </span>
                <NuxtButton icon="i-lucide-x" size="xs" color="neutral" variant="ghost" square :aria-label="`Tirar ${order(ref).code}`" @click="toggle(ref)" />
              </li>
            </ol>
          </section>
          <NuxtButton v-if="rides.length < COLORS.length && free.length" icon="i-lucide-plus" label="Nova corrida" color="neutral" variant="ghost" class="self-start" @click="newRide" />
        </div>

        <div v-if="free.length" class="mt-4 flex flex-col gap-1">
          <p class="op-micro font-semibold text-muted">Sem corrida · {{ free.length }}</p>
          <button
            v-for="o in free"
            :key="o.ref"
            type="button"
            class="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition hover:bg-elevated"
            @click="toggle(o.ref)"
          >
            <span class="grid size-6 shrink-0 place-items-center rounded-full border-2 bg-white op-micro font-semibold" style="border-color:#b9a888;color:#5b4a2c">+</span>
            <span class="min-w-0 flex-1 truncate op-body"><span class="font-medium text-highlighted">{{ o.code }} · {{ o.customer }}</span> <span class="text-muted">· {{ o.place }}</span></span>
            <span class="op-micro text-muted">{{ o.stage }}</span>
          </button>
        </div>
      </div>
      <div class="flex items-center gap-3 border-t border-default p-4">
        <p class="min-w-0 flex-1 op-body text-muted">
          <template v-if="ready.length">{{ ready.reduce((s, r) => s + r.length, 0) }} pedidos em {{ ready.length }} {{ ready.length === 1 ? "corrida" : "corridas" }}<template v-if="free.length"> · {{ free.length }} ficam</template></template>
          <template v-else>Nenhuma corrida montada.</template>
        </p>
        <NuxtButton size="lg" icon="i-lucide-bike" :label="callLabel" :disabled="!ready.length" />
      </div>
    </div>
  </div>
</template>
