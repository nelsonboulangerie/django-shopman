<script setup lang="ts">
// A seção Entregas: a casa das corridas da TaOn (desenho do dono, 14/11/2026, PR #2462).
//
// Mapa à esquerda, coluna à direita, as MESMAS três partes nos dois:
//  1. Aguardando: entregas do dia sem corrida chamada (projeção ``deliveries``).
//  2. Editando: as corridas que o operador está juntando, cada uma com a sua letra
//     e cor (a letra é o nome da corrida; o número só escolhe a cor e a letra).
//     Estado só da tela: nada é gravado até "Chamar".
//  3. Corridas: as chamadas, vivas. No mapa a rota fica a 50% e só a moto leva a
//     cor cheia; na coluna, cada uma é um espelho que abre o detalhe (`?ride=<chave>`).
import type {
  DeliveriesProjection,
  DeliveryRideProjection,
  DeliveryStopProjection,
} from "~/generated/ordersContract";
import type { MapLiveRide, MapPoint } from "~/components/CourierDeliveriesMap.vue";
import { rideColor } from "~/presentation/ridePalette";
import type { OperatorActionBarAction } from "../../../operator-kit/app/presentation/actionBar";
import {
  needsMachine,
  nextFreeNumber,
  rideCalls,
  rideLetter,
  type EditingRide,
} from "~/presentation/deliveries";

const route = useRoute();
const router = useRouter();
const intentions = useOrderIntention();

const { data, pending, error, refresh } = useFetch<DeliveriesProjection>(
  "/api/v1/backstage/deliveries/",
  { key: "orders:deliveries", server: false },
);
useBackstageEvents("orders", () => void refresh(), { pollMs: 20_000 });
const now = ref(Date.now());
let clock: ReturnType<typeof setInterval> | undefined;
onMounted(() => (clock = setInterval(() => (now.value = Date.now()), 30_000)));
onBeforeUnmount(() => clearInterval(clock));

const waitingAll = computed(() => data.value?.waiting ?? []);
const rides = computed(() => data.value?.rides ?? []);
const maxStops = computed(() => data.value?.max_stops ?? 4);
const byRef = computed(() => new Map(waitingAll.value.map((stop) => [stop.ref, stop])));

// ── editando ────────────────────────────────────────────────────────────────
const editing = ref<EditingRide[]>([]);
const active = ref(0);
// Os números livres vêm do servidor (`free_numbers`: as corridas na rua já
// descontadas, até 26 letras); a tela só desconta as que ela mesma está editando.
const freeNumbers = computed(() => data.value?.free_numbers ?? []);
const editingNumbers = computed(() => editing.value.map((ride) => ride.number));
function ensureEditing() {
  if (editing.value.length) return;
  const number = nextFreeNumber(freeNumbers.value, []) ?? 1;
  editing.value = [{ number, refs: [] }];
  active.value = number;
}
watch(freeNumbers, (free) => {
  // Uma corrida chamada enquanto se editava (em outro dispositivo) pode ter pego o
  // número (e com ele a letra): a editada troca para um livre.
  for (const ride of editing.value) {
    if (free.includes(ride.number)) continue;
    const next = nextFreeNumber(free, editing.value.filter((r) => r !== ride).map((r) => r.number));
    if (!next) continue;
    if (active.value === ride.number) active.value = next;
    ride.number = next;
  }
});
// O que sumiu da lista (chamado em outro lugar, cancelado) sai da edição.
watch(waitingAll, (list) => {
  const alive = new Set(list.map((stop) => stop.ref));
  for (const ride of editing.value) ride.refs = ride.refs.filter((ref) => alive.has(ref));
});
const activeRide = computed(() => editing.value.find((ride) => ride.number === active.value));
const rideOf = (ref: string) => editing.value.find((ride) => ride.refs.includes(ref));
function toggle(ref: string) {
  ensureEditing();
  const mine = activeRide.value!;
  const at = rideOf(ref);
  if (at === mine) {
    mine.refs = mine.refs.filter((item) => item !== ref);
    return;
  }
  if (mine.refs.length >= maxStops.value) return;
  if (at) at.refs = at.refs.filter((item) => item !== ref);
  mine.refs = [...mine.refs, ref];
}
function fill(place: string) {
  ensureEditing();
  const mine = activeRide.value!;
  const refs = waitingAll.value
    .filter((stop) => stop.place === place && !stop.group_refusal && (!rideOf(stop.ref) || rideOf(stop.ref) === mine))
    .map((stop) => stop.ref);
  mine.refs = refs.slice(0, maxStops.value);
}
function newRide() {
  const number = nextFreeNumber(freeNumbers.value, editingNumbers.value);
  if (!number) return;
  editing.value.push({ number, refs: [] });
  active.value = number;
}
function drop(number: number) {
  editing.value = editing.value.filter((ride) => ride.number !== number);
  if (active.value === number) active.value = editing.value[0]?.number ?? 0;
}
function openFromMap(number: number) {
  const ride = rides.value.find((item) => item.number === number);
  if (ride) open(ride);
}
const waiting = computed(() => waitingAll.value.filter((stop) => !rideOf(stop.ref)));
const ready = computed(() => editing.value.filter((ride) => ride.refs.length));
const suggestions = computed(() => {
  const count = new Map<string, number>();
  for (const stop of waitingAll.value) {
    if (stop.group_refusal || !stop.place) continue;
    if (rideOf(stop.ref) && rideOf(stop.ref) !== activeRide.value) continue;
    count.set(stop.place, (count.get(stop.place) ?? 0) + 1);
  }
  return [...count.entries()].filter(([, n]) => n >= 2).map(([place, n]) => ({ place, n }));
});
const canAddRide = computed(
  () => waiting.value.length > 0 && nextFreeNumber(freeNumbers.value, editingNumbers.value) !== null && editing.value.every((ride) => ride.refs.length),
);

// ── chamar ──────────────────────────────────────────────────────────────────
const machines = computed(() => data.value?.machines ?? []);
const machineRef = ref("");
const wantsMachine = computed(() => needsMachine(ready.value, waitingAll.value));
watch(
  machines,
  (list) => {
    if (list.length === 1) machineRef.value = String(list[0]!.ref);
  },
  { immediate: true },
);
const machineItems = computed(() => machines.value.map((m) => ({ label: String(m.label), value: String(m.ref) })));
const sending = ref(false);
const failure = ref("");
const callLabel = computed(() =>
  ready.value.length === 1 ? `Chamar a corrida ${rideLetter(ready.value[0]!.number)}` : `Chamar ${ready.value.length} corridas`,
);
const canCall = computed(
  () => ready.value.length > 0 && !sending.value && (!wantsMachine.value || Boolean(machineRef.value)),
);
const callContext = computed(
  () => `${editingCount.value} ${editingCount.value === 1 ? "pedido" : "pedidos"} em ${ready.value.length} ${ready.value.length === 1 ? "corrida" : "corridas"}`,
);
const callAction = computed<OperatorActionBarAction>(() => ({
  label: callLabel.value,
  shortLabel: "Chamar",
  icon: "i-lucide-bike",
  loading: sending.value,
  disabled: !canCall.value,
  reason: wantsMachine.value && !machineRef.value ? "Escolha a maquininha que vai." : "",
  onSelect: () => void call(),
}));
async function call() {
  sending.value = true;
  failure.value = "";
  const calls = rideCalls(ready.value, waitingAll.value, machineRef.value);
  const called: string[] = [];
  // A corrida que já existia com os mesmos pedidos (chamada em outro dispositivo):
  // o servidor diz, e a frase é a dele.
  let already = "";
  try {
    for (const item of calls) {
      if (item.kind === "group") {
        // Pelo protocolo de intenção, como a chamada de um pedido só: quem a tela
        // leu, a revisão de cada pedido e uma chave por corrida, guardada até a
        // resposta definitiva (`group_action` da projeção).
        const result = await intentions.executeRide(data.value?.group_action, {
          refs: item.refs,
          change_out: item.change_out,
          machine: item.machine,
          ride_number: item.number,
        });
        if (result.already_called && result.detail) already = result.detail;
      } else {
        const ref = item.refs[0]!;
        await intentions.execute(ref, "courier-dispatch", byRef.value.get(ref)?.dispatch_action ?? undefined, {
          ...(item.change_out[ref] ? { change_out: item.change_out[ref] } : {}),
          ...(item.machine ? { equipment: [item.machine] } : {}),
          ride_number: item.number,
        });
      }
      called.push(...item.refs);
    }
    useSonner.success(
      calls.length === 1
        ? already || "Corrida chamada. A TaOn avisa quando alguém aceitar."
        : `${calls.length} corridas chamadas.`,
    );
  } catch (err) {
    failure.value = httpErrorMessage(err, "Não foi possível chamar. Confira as corridas e tente de novo.");
  } finally {
    const done = new Set(called);
    editing.value = editing.value.filter((ride) => !ride.refs.some((ref) => done.has(ref)));
    active.value = editing.value[0]?.number ?? 0;
    sending.value = false;
    await refresh();
  }
}

// ── corridas: detalhe e gestos ───────────────────────────────────────────────
const openKey = computed(() => String(route.query.ride || ""));
// A corrida aberta se identifica pela chave dela (`ride.key`), não pelo número: o
// número volta a ficar livre quando a corrida fecha e outra o pega.
const openRide = computed(() => rides.value.find((ride) => ride.key === openKey.value));
function open(ride: DeliveryRideProjection) {
  void router.replace({ query: { ...route.query, ride: ride.key } });
}
function close() {
  void router.replace({ query: { ...route.query, ride: undefined } });
}
const busyRide = ref("");
async function rideAction(ride: DeliveryRideProjection, operation: "courier-back" | "courier-cancel") {
  const action = operation === "courier-back" ? ride.back_action : ride.cancel_action;
  busyRide.value = ride.key;
  try {
    await intentions.execute(ride.lead_ref, operation, action ?? undefined, {});
    useSonner.success(operation === "courier-back" ? "Saída fechada." : "Cancelamento pedido à TaOn.");
  } catch (err) {
    useSonner.error(httpErrorMessage(err, "Não foi possível. Atualize e tente de novo."));
  } finally {
    busyRide.value = "";
    await refresh();
  }
}

// ── mapa ────────────────────────────────────────────────────────────────────
type Located = DeliveryStopProjection & { latitude: number; longitude: number };
const located = (stop: DeliveryStopProjection): stop is Located =>
  stop.latitude !== null && stop.longitude !== null;
const mapWaiting = computed<MapPoint[]>(() =>
  waiting.value.filter(located).map((stop) => ({ ...stop, preparing: stop.stage !== "Pronto" })),
);
const mapBuilding = computed(() =>
  editing.value.map((ride) => ({
    number: ride.number,
    stops: ride.refs
      .map((ref) => byRef.value.get(ref))
      .filter((stop): stop is DeliveryStopProjection => Boolean(stop))
      .filter(located),
  })),
);
const mapLive = computed<MapLiveRide[]>(() =>
  rides.value.map((ride) => ({ number: ride.number, stops: ride.stops.filter(located), courier: ride.position })),
);
const origin = computed(
  () => data.value?.origin ?? mapWaiting.value[0] ?? mapLive.value[0]?.stops[0] ?? null,
);
const unlocated = computed(() => waitingAll.value.filter((stop) => !located(stop)).length);
const editingCount = computed(() => ready.value.reduce((sum, ride) => sum + ride.refs.length, 0));
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-deliveries-page>
    <OperatorPageHeader title="Entregas" :filters-wrap="false">
      <template #status>
        <span class="op-micro text-muted">
          {{ waiting.length }} aguardando · {{ editingCount }} editando · {{ rides.length }} {{ rides.length === 1 ? "corrida" : "corridas" }}
        </span>
      </template>
    </OperatorPageHeader>

    <OperatorScreenState v-if="error && !data" state="error" what="as entregas" class="m-4" />
    <div v-else-if="pending && !data" class="grid flex-1 place-items-center p-6"><NuxtSkeleton class="h-64 w-full max-w-3xl" /></div>
    <NuxtEmpty
      v-else-if="data && !data.courier_on"
      icon="i-lucide-bike"
      title="A integração com a TaOn não está ligada."
      description="As entregas aparecem aqui quando a central estiver configurada."
      class="m-6"
    />

    <div v-else-if="data" class="flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-2 lg:grid-rows-[minmax(0,1fr)]">
      <div class="h-[38dvh] shrink-0 border-b border-default lg:h-auto lg:border-r lg:border-b-0">
        <CourierDeliveriesMap
          v-if="origin"
          :origin="origin"
          :waiting="mapWaiting"
          :building="mapBuilding"
          :live="mapLive"
          :active="active"
          :live-opacity="0.5"
          :maps-key="data.maps_key"
          @toggle="toggle"
          @fill="fill"
          @open="openFromMap"
        />
        <NuxtEmpty v-else icon="i-lucide-map" title="Nada no mapa agora." class="h-full" />
      </div>

      <div class="flex min-h-0 flex-col">
        <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4 lg:px-5">
          <!-- 1. aguardando -->
          <section>
            <h2 class="flex items-center gap-2 op-label font-semibold text-highlighted">
              <span class="size-3 rounded-full border-2 bg-white" style="border-color: #b9a888" />
              Aguardando
              <OperatorCountChip :count="waiting.length" />
            </h2>
            <p v-if="!waitingAll.length" class="mt-2 op-body text-muted">Nenhuma entrega aguardando entregador.</p>
            <div v-if="suggestions.length" class="mt-2 flex flex-wrap gap-1.5">
              <NuxtButton v-for="s in suggestions" :key="s.place" color="neutral" variant="outline" icon="i-lucide-map-pin" :label="`${s.place} · ${s.n}`" @click="fill(s.place)" />
            </div>
            <ul class="mt-2 flex flex-col">
              <li v-for="stop in waiting" :key="stop.ref">
                <NuxtButton color="neutral" variant="ghost" block class="justify-start gap-2.5 text-left" @click="toggle(stop.ref)">
                  <span class="grid size-6 shrink-0 place-items-center rounded-full border-2 bg-white text-toned" style="border-color: #b9a888"><NuxtIcon name="i-lucide-plus" class="size-3.5" /></span>
                  <span class="min-w-0 flex-1">
                    <span class="block truncate op-body"><span class="font-medium text-highlighted">{{ stop.code }} · {{ stop.customer }}</span> <span class="text-muted">· {{ stop.place }}</span></span>
                    <span v-if="stop.error" class="block truncate op-micro text-error">{{ stop.error }}</span>
                    <span v-else-if="stop.change_label || stop.needs_machine" class="block truncate op-micro text-muted">{{ [stop.change_label, stop.needs_machine ? "Leva a maquininha" : ""].filter(Boolean).join(" · ") }}</span>
                  </span>
                  <NuxtBadge v-if="stop.stage !== 'Pronto'" :label="stop.stage" color="warning" icon="i-lucide-chef-hat" />
                </NuxtButton>
              </li>
            </ul>
            <p v-if="unlocated" class="mt-1 px-2 op-micro text-muted">{{ unlocated }} sem localização no endereço: estão na lista, não no mapa.</p>
          </section>

          <!-- 2. editando -->
          <section v-if="editing.length" class="mt-5">
            <h2 class="flex items-center gap-2 op-label font-semibold text-highlighted">
              <NuxtIcon name="i-lucide-route" class="size-4 text-muted" />
              Editando
              <OperatorCountChip :count="editing.length" />
            </h2>
            <div class="mt-2 flex flex-col gap-2">
              <section
                v-for="ride in editing"
                :key="ride.number"
                class="rounded-xl border transition"
                :style="ride.number === active ? { borderColor: rideColor(ride.number - 1).bg, boxShadow: `0 0 0 3px ${rideColor(ride.number - 1).bg}2e` } : {}"
                :class="ride.number === active ? 'bg-default' : 'border-default bg-elevated/50'"
              >
                <div class="flex w-full items-center gap-2 px-3 py-2.5">
                  <NuxtButton color="neutral" variant="ghost" class="min-w-0 flex-1 justify-start gap-2 p-0 text-left" :aria-pressed="ride.number === active" @click="active = ride.number">
                    <span class="grid h-6 min-w-6 shrink-0 place-items-center rounded-md px-1.5 op-micro font-bold" :style="{ background: rideColor(ride.number - 1).bg, color: rideColor(ride.number - 1).fg }">{{ rideLetter(ride.number) }}</span>
                    <span class="op-label font-semibold text-highlighted">Corrida {{ rideLetter(ride.number) }}</span>
                    <span class="op-micro tabular-nums text-muted">{{ ride.refs.length }} de {{ maxStops }}</span>
                    <span v-if="ride.number !== active && ride.refs.length" class="ml-1 min-w-0 flex-1 truncate op-micro text-muted">{{ ride.refs.map((ref) => byRef.get(ref)?.code ?? ref).join(" → ") }}</span>
                  </NuxtButton>
                  <NuxtButton icon="i-lucide-trash-2" color="neutral" variant="ghost" square :aria-label="`Desfazer a corrida ${rideLetter(ride.number)}`" @click="drop(ride.number)" />
                </div>
                <ol v-if="ride.number === active" class="flex flex-col gap-1 px-3 pb-3">
                  <li v-if="!ride.refs.length" class="rounded-lg border border-dashed border-default px-3 py-3 text-center op-body text-muted">Toque nos pedidos no mapa ou na lista.</li>
                  <li v-for="(ref, k) in ride.refs" :key="ref" class="flex items-center gap-2.5 rounded-lg bg-elevated/60 px-2 py-1.5">
                    <span class="grid size-6 shrink-0 place-items-center rounded-full border-[3px] border-dotted bg-white op-micro font-bold text-highlighted" :style="{ borderColor: rideColor(ride.number - 1).bg }">{{ k + 1 }}</span>
                    <span class="min-w-0 flex-1">
                      <span class="block truncate op-body font-medium text-highlighted">{{ byRef.get(ref)?.code }} · {{ byRef.get(ref)?.customer }}</span>
                      <span class="block truncate op-micro text-muted">{{ [byRef.get(ref)?.place, byRef.get(ref)?.change_label].filter(Boolean).join(" · ") }}</span>
                    </span>
                    <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square :aria-label="`Tirar ${byRef.get(ref)?.code}`" @click="toggle(ref)" />
                  </li>
                  <li v-if="ride.refs.length > 1" class="px-1 pt-1 op-micro text-muted">A TaOn leva na ordem do percurso, a partir da loja.</li>
                </ol>
              </section>
            </div>
          </section>
          <NuxtButton v-if="canAddRide" class="mt-2" icon="i-lucide-plus" :label="editing.length ? 'Nova corrida' : 'Montar uma corrida'" color="neutral" variant="ghost" @click="editing.length ? newRide() : ensureEditing()" />

          <!-- 3. corridas -->
          <section class="mt-5 pb-2">
            <h2 class="flex items-center gap-2 op-label font-semibold text-highlighted">
              <NuxtIcon name="i-lucide-bike" class="size-4 text-muted" />
              Corridas
              <OperatorCountChip :count="rides.length" />
            </h2>
            <p v-if="!rides.length" class="mt-2 op-body text-muted">Nenhuma corrida na rua.</p>
            <div class="mt-2 flex flex-col gap-2">
              <CourierRideMirror
                v-for="ride in rides"
                :key="ride.key"
                :ride="ride"
                :now="now"
                :busy="busyRide === ride.key"
                @back="rideAction(ride, 'courier-back')"
              />
            </div>
          </section>
        </div>

        <div v-if="ready.length" class="flex flex-col gap-2 border-t border-default bg-default p-4">
          <p v-if="failure" class="op-body text-error" aria-live="assertive">{{ failure }}</p>
          <div v-if="wantsMachine && machines.length > 1" class="flex items-center gap-2">
            <p class="op-body text-toned">Maquininha que vai:</p>
            <NuxtSelect v-model="machineRef" :items="machineItems" placeholder="Escolha" class="min-w-40" />
          </div>
          <p v-else-if="wantsMachine && !machines.length" class="op-body text-warning">Nenhuma maquininha livre para a corrida com cartão.</p>
          <div class="flex items-center gap-3">
            <p class="min-w-0 flex-1 op-body text-muted">
              {{ editingCount }} {{ editingCount === 1 ? "pedido" : "pedidos" }} em {{ ready.length }} {{ ready.length === 1 ? "corrida" : "corridas" }}<template v-if="waiting.length"> · {{ waiting.length }} ficam</template>
            </p>
            <NuxtButton class="hidden lg:inline-flex" icon="i-lucide-bike" :label="callLabel" :loading="sending" :disabled="!canCall" @click="call" />
          </div>
        </div>
      </div>
    </div>

    <!-- No celular, o "Chamar" é a ação do momento na base (kit). -->
    <OperatorActionBar v-if="ready.length" :action="callAction" :context-label="callContext" label="Chamar as corridas" />

    <NuxtSlideover
      :open="Boolean(openRide && data)"
      side="right"
      class="sm:max-w-lg"
      :title="openRide ? `Corrida ${openRide.letter}` : 'Corrida'"
      description="O andamento da corrida, o entregador e as paradas."
      @update:open="(value: boolean) => { if (!value) close(); }"
    >
      <template #content>
        <CourierRideDetail
          v-if="openRide && data"
          :ride="openRide"
          :origin="data.origin"
          :maps-key="data.maps_key"
          :now="now"
          :busy="busyRide === openRide.key"
          @close="close"
          @back="rideAction(openRide, 'courier-back')"
          @cancel="rideAction(openRide, 'courier-cancel')"
        />
      </template>
    </NuxtSlideover>
  </main>
</template>
