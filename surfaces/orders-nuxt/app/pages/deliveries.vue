<script setup lang="ts">
// PRÉVIA (14/11) — a seção Entregas: a casa das corridas da TaOn. Dados de exemplo,
// não vai ao ar assim.
//
// Mapa à esquerda, coluna à direita, as MESMAS três partes nos dois:
//  1. Esperando entregador: pedidos de entrega prontos (ou quase) sem corrida.
//  2. Montando: as corridas que o operador está juntando, cada uma com a sua cor.
//     "Chamar N corridas" chama todas de uma vez.
//  3. Na rua: as corridas já chamadas. No mapa a rota fica cinza e só a moto leva a
//     cor; na coluna, cada uma é o mesmo ESPELHO que o Painel mostra.
// Tocar numa corrida da rua (linha, moto ou parada) abre o detalhe ao lado
// (`?ride=N`): é o mesmo endereço a que o espelho do Painel leva.
import { rideColor } from "~/presentation/ridePalette";
import type { MapLiveRide, MapPoint } from "~/components/CourierDeliveriesMap.vue";

const MAX = 4;
const route = useRoute();
const router = useRouter();
const openRide = computed(() => Number(route.query.ride) || 0);
const open = (n: number) => router.replace({ query: { ...route.query, ride: String(n) } });
const close = () => router.replace({ query: { ...route.query, ride: undefined } });

const C: Record<string, [number, number]> = {
  "Gleba Palhano": [-23.331, -51.181], Centro: [-23.309, -51.161], "Jardim Higienópolis": [-23.319, -51.148], "Bela Suíça": [-23.343, -51.165],
};
type Row = [string, string, string, number, number, boolean?];
const pt = ([code, customer, place, dl, dg, preparing]: Row) => ({
  ref: code, code, customer, place, latitude: C[place]![0] + dl, longitude: C[place]![1] + dg, preparing: Boolean(preparing),
});
const origin = { latitude: -23.3105, longitude: -51.1695 };

// Pedidos sem corrida chamada: esperando ou montando.
const pool = ([
  ["A12", "Maria Santos", "Gleba Palhano", 0.002, -0.001],
  ["A14", "João Oliveira", "Gleba Palhano", -0.0015, 0.002],
  ["A17", "Pedro Alves", "Gleba Palhano", -0.001, -0.0025, true],
  ["A18", "Fernanda Dias", "Gleba Palhano", 0.0022, 0.0028],
  ["B03", "Ana Lima", "Centro", 0.001, 0.0025],
  ["B05", "Beatriz Rocha", "Centro", 0.0025, 0.001],
  ["B09", "Juliana Mendes", "Centro", 0.0005, -0.002],
  ["C04", "Carlos Souza", "Jardim Higienópolis", -0.002, -0.0015, true],
  ["C08", "Rafael Costa", "Jardim Higienópolis", -0.0025, 0.001],
  ["D07", "Lúcia Ferreira", "Bela Suíça", 0.0015, 0.0015],
  ["D10", "Tiago Martins", "Bela Suíça", -0.001, 0.002],
] as Row[]).map(pt);
const byRef = (ref: string) => pool.find((o) => o.ref === ref)!;

// As corridas na rua. As cores 1 a 3 estão com elas; montar começa na 4.
const live = [
  { number: 1, state: "atStore" as const, courier: "Diego", stops: [pt(["A02", "Bruno Reis", "Gleba Palhano", 0.0035, 0.004]), pt(["A05", "Cíntia Melo", "Gleba Palhano", -0.003, 0.0045])], at: { latitude: -23.3135, longitude: -51.1662 } },
  { number: 2, state: "coming" as const, courier: "Rita", eta: "6 min", stops: [pt(["B01", "Davi Prado", "Centro", -0.0028, -0.004]), pt(["B02", "Elisa Cunha", "Centro", 0.0035, -0.0035])], at: { latitude: -23.3025, longitude: -51.1735 } },
  { number: 3, state: "route" as const, courier: "Léo", eta: "12:49", stops: [{ ...pt(["D01", "Lúcia Ferreira", "Bela Suíça", 0.004, -0.004]), done: true }, pt(["D02", "Tiago Martins", "Bela Suíça", -0.003, -0.003]), pt(["D03", "Sofia Ramos", "Bela Suíça", -0.0045, 0.0045])], at: { latitude: -23.3405, longitude: -51.1695 } },
];
const mapLive = computed<MapLiveRide[]>(() => live.map((r) => ({ number: r.number, stops: r.stops, courier: r.at })));

// Montando: números (e cores) a partir do primeiro livre.
const building = ref<{ number: number; refs: string[] }[]>([
  { number: 4, refs: ["A12", "A14", "A18"] },
  { number: 5, refs: ["B03", "B09"] },
]);
const active = ref(5);
const rideOf = (ref: string) => building.value.find((r) => r.refs.includes(ref));
const activeRide = computed(() => building.value.find((r) => r.number === active.value)!);
function toggle(ref: string) {
  const at = rideOf(ref);
  const mine = activeRide.value;
  if (at === mine) { mine.refs = mine.refs.filter((r) => r !== ref); return; }
  if (mine.refs.length >= MAX) return;
  if (at) at.refs = at.refs.filter((r) => r !== ref);
  mine.refs.push(ref);
}
function fill(place: string) {
  const refs = pool.filter((o) => o.place === place && (!rideOf(o.ref) || rideOf(o.ref) === activeRide.value)).map((o) => o.ref);
  activeRide.value.refs = refs.slice(0, MAX);
}
const usedNumbers = computed(() => [...live.map((r) => r.number), ...building.value.map((r) => r.number)]);
function newRide() {
  const next = [1, 2, 3, 4, 5, 6].find((n) => !usedNumbers.value.includes(n));
  if (!next) return;
  building.value.push({ number: next, refs: [] });
  active.value = next;
}
function drop(n: number) {
  building.value = building.value.filter((r) => r.number !== n);
  if (!building.value.length) building.value.push({ number: 4, refs: [] });
  if (!building.value.some((r) => r.number === active.value)) active.value = building.value[0]!.number;
}
const waiting = computed(() => pool.filter((o) => !rideOf(o.ref)));
const ready = computed(() => building.value.filter((r) => r.refs.length));
const suggestions = computed(() => {
  const n = new Map<string, number>();
  for (const o of pool) if (!rideOf(o.ref) || rideOf(o.ref) === activeRide.value) n.set(o.place, (n.get(o.place) || 0) + 1);
  return [...n.entries()].filter(([, k]) => k >= 2).map(([place, k]) => ({ place, n: k }));
});
const mapWaiting = computed<MapPoint[]>(() => waiting.value);
const mapBuilding = computed(() => building.value.map((r) => ({ number: r.number, stops: r.refs.map(byRef) })));
const callLabel = computed(() =>
  ready.value.length === 1 ? `Chamar a corrida ${ready.value[0]!.number}` : `Chamar ${ready.value.length} corridas`,
);
const quotes: Record<number, string> = { 4: "R$ 18,40 · 24 min", 5: "R$ 11,90 · 17 min" };
</script>

<template>
  <div class="flex min-h-dvh flex-col lg:h-dvh" data-deliveries-page>
    <header class="flex items-center gap-3 border-b border-default px-4 py-3 lg:px-6">
      <div class="min-w-0 flex-1">
        <h1 class="op-title font-semibold text-highlighted">Entregas</h1>
        <p class="op-body text-muted">{{ waiting.length }} esperando · {{ ready.reduce((s, r) => s + r.refs.length, 0) }} montando · {{ live.length }} corridas na rua</p>
      </div>
      <NuxtBadge color="success" variant="soft" icon="i-lucide-radio" label="TaOn em dia" class="hidden sm:inline-flex" />
    </header>

    <div class="flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-2">
      <!-- o mapa -->
      <div class="h-[38dvh] shrink-0 border-b border-default lg:h-auto lg:border-r lg:border-b-0">
        <CourierDeliveriesMap :origin="origin" :waiting="mapWaiting" :building="mapBuilding" :live="mapLive" :active="active" @toggle="toggle" @fill="fill" @open="open" />
      </div>

      <!-- a coluna: as mesmas três partes -->
      <div class="flex min-h-0 flex-col">
        <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4 lg:px-5">
          <!-- 1. esperando -->
          <section>
            <h2 class="flex items-center gap-2 op-label font-semibold text-highlighted">
              <span class="size-3 rounded-full border-2 bg-white" style="border-color:#b9a888" />
              Esperando entregador
              <NuxtBadge :label="String(waiting.length)" color="neutral" variant="soft" size="sm" />
            </h2>
            <div v-if="suggestions.length" class="mt-2 flex flex-wrap gap-1.5">
              <NuxtButton v-for="s in suggestions" :key="s.place" size="sm" color="neutral" variant="outline" icon="i-lucide-map-pin" :label="`${s.place} · ${s.n}`" @click="fill(s.place)" />
            </div>
            <ul class="mt-2 flex flex-col">
              <li v-for="o in waiting" :key="o.ref">
                <button type="button" class="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition hover:bg-elevated" @click="toggle(o.ref)">
                  <span class="grid size-6 shrink-0 place-items-center rounded-full border-2 bg-white text-toned" style="border-color:#b9a888"><NuxtIcon name="i-lucide-plus" class="size-3.5" /></span>
                  <span class="min-w-0 flex-1 truncate op-body"><span class="font-medium text-highlighted">{{ o.code }} · {{ o.customer }}</span> <span class="text-muted">· {{ o.place }}</span></span>
                  <NuxtBadge v-if="o.preparing" label="Em preparo" color="warning" variant="soft" size="sm" icon="i-lucide-chef-hat" />
                </button>
              </li>
            </ul>
          </section>

          <!-- 2. montando -->
          <section class="mt-5">
            <h2 class="flex items-center gap-2 op-label font-semibold text-highlighted">
              <NuxtIcon name="i-lucide-route" class="size-4 text-muted" />
              Montando
              <NuxtBadge :label="String(building.length)" color="neutral" variant="soft" size="sm" />
            </h2>
            <div class="mt-2 flex flex-col gap-2">
              <section
                v-for="r in building"
                :key="r.number"
                class="rounded-xl border transition"
                :style="r.number === active ? { borderColor: rideColor(r.number - 1).bg, boxShadow: `0 0 0 3px ${rideColor(r.number - 1).bg}2e` } : {}"
                :class="r.number === active ? 'bg-default' : 'border-default bg-elevated/50'"
              >
                <button type="button" class="flex w-full items-center gap-2 px-3 py-2.5 text-left" @click="active = r.number">
                  <span class="grid h-6 min-w-6 shrink-0 place-items-center rounded-md px-1.5 op-micro font-bold" :style="{ background: rideColor(r.number - 1).bg, color: rideColor(r.number - 1).fg }">{{ r.number }}</span>
                  <span class="op-label font-semibold text-highlighted">Corrida {{ r.number }}</span>
                  <span class="op-micro tabular-nums text-muted">{{ r.refs.length }} de {{ MAX }}</span>
                  <span v-if="r.number !== active && r.refs.length" class="ml-1 min-w-0 flex-1 truncate op-micro text-muted">{{ r.refs.join(" → ") }}</span>
                  <span v-else class="flex-1" />
                  <span v-if="r.refs.length && quotes[r.number]" class="op-micro tabular-nums text-muted">{{ quotes[r.number] }}</span>
                  <NuxtButton icon="i-lucide-trash-2" size="xs" color="neutral" variant="ghost" square :aria-label="`Desfazer a corrida ${r.number}`" @click.stop="drop(r.number)" />
                </button>
                <ol v-if="r.number === active" class="flex flex-col gap-1 px-3 pb-3">
                  <li v-if="!r.refs.length" class="rounded-lg border border-dashed border-default px-3 py-3 text-center op-body text-muted">Toque nos pedidos no mapa ou na lista.</li>
                  <li v-for="(ref, k) in r.refs" :key="ref" class="flex items-center gap-2.5 rounded-lg bg-elevated/60 px-2 py-1.5">
                    <span class="grid size-6 shrink-0 place-items-center rounded-full border-[3px] bg-white op-micro font-bold text-highlighted" :style="{ borderColor: rideColor(r.number - 1).bg }">{{ k + 1 }}</span>
                    <span class="min-w-0 flex-1">
                      <span class="block truncate op-body font-medium text-highlighted">{{ byRef(ref).code }} · {{ byRef(ref).customer }}</span>
                      <span class="block truncate op-micro text-muted">{{ byRef(ref).place }}</span>
                    </span>
                    <NuxtButton icon="i-lucide-x" size="xs" color="neutral" variant="ghost" square :aria-label="`Tirar ${ref}`" @click="toggle(ref)" />
                  </li>
                  <li class="px-1 pt-1 op-micro text-muted">A TaOn leva na ordem do percurso, a partir da loja.</li>
                </ol>
              </section>
              <NuxtButton v-if="usedNumbers.length < 6 && waiting.length" icon="i-lucide-plus" label="Nova corrida" color="neutral" variant="ghost" class="self-start" @click="newRide" />
            </div>
          </section>

          <!-- 3. na rua -->
          <section class="mt-5 pb-2">
            <h2 class="flex items-center gap-2 op-label font-semibold text-highlighted">
              <NuxtIcon name="i-lucide-bike" class="size-4 text-muted" />
              Na rua
              <NuxtBadge :label="String(live.length)" color="neutral" variant="soft" size="sm" />
            </h2>
            <div class="mt-2 flex flex-col gap-2">
              <CourierRideMirror
                v-for="r in live"
                :key="r.number"
                :number="r.number"
                :state="r.state"
                :courier="r.courier"
                :eta="r.eta"
                :stops="r.stops.map((s) => ({ code: s.code, done: 'done' in s && Boolean(s.done) }))"
              />
            </div>
          </section>
        </div>

        <!-- o chamar, sempre à vista -->
        <div class="sticky bottom-0 flex items-center gap-3 border-t border-default bg-default p-4">
          <p class="min-w-0 flex-1 op-body text-muted">
            <template v-if="ready.length">{{ ready.reduce((s, r) => s + r.refs.length, 0) }} pedidos em {{ ready.length }} {{ ready.length === 1 ? "corrida" : "corridas" }}<template v-if="waiting.length"> · {{ waiting.length }} ficam</template></template>
            <template v-else>Nenhuma corrida montada.</template>
          </p>
          <NuxtButton size="lg" icon="i-lucide-bike" :label="callLabel" :disabled="!ready.length" />
        </div>
      </div>
    </div>

    <!-- o detalhe da corrida, ao lado (tela cheia no celular) -->
    <div v-if="openRide" class="fixed inset-0 z-50 flex justify-end bg-black/30" @click.self="close">
      <CourierRideDetail :number="openRide" @close="close" />
    </div>
  </div>
</template>
