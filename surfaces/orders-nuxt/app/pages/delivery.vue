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
import { PIN_TEXT } from "~/presentation/deliveriesMap";
import type { OperatorActionBarAction } from "../../../operator-kit/app/presentation/actionBar";
import {
  assignMachines,
  backCheck,
  callAllLabel,
  callSummary,
  changeValue,
  failureStops,
  machineShortfall,
  nextFreeNumber,
  quoteLines,
  rideCalls,
  rideFailureTitle,
  rideLetter,
  ridesFromSuggestions,
  ridesNeedingMachine,
  routeOrder,
  suggestionLate,
  suggestionOrder,
  suggestionQuoteLines,
  suggestionsHeadline,
  toggleStop,
  visibleSuggestions,
  type EditingRide,
  type RideFailure,
  type RideSuggestion,
} from "~/presentation/deliveries";
import type { CallSheetRide } from "~/components/CourierCallSheet.vue";

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
  // A regra mora em `toggleStop`: pedido recusado não entra, e a corrida cheia
  // manda o pedido para a próxima, sempre dizendo o que fez.
  const result = toggleStop(editing.value, active.value, ref, waitingAll.value, maxStops.value, freeNumbers.value);
  editing.value = result.editing;
  active.value = result.active;
  if (result.notice) useSonner.info(result.notice);
}
// O toque no nome do bairro no mapa SOMA à corrida ativa os prontos dali que estão
// livres, até caber (nunca apaga o que o operador já escolheu, nunca pega pedido em
// preparo: a casa não sabe a hora em que ele fica pronto).
function fill(place: string) {
  ensureEditing();
  const mine = activeRide.value!;
  const add = waitingAll.value
    .filter((stop) => stop.place === place && stop.stage === "Pronto" && !stop.group_refusal && !stop.dispatch_again_action && !rideOf(stop.ref))
    .map((stop) => stop.ref);
  mine.refs = [...mine.refs, ...add].slice(0, Math.max(maxStops.value, mine.refs.length));
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
// ── sugestões da casa (ride_plan, F5) ───────────────────────────────────────
// O MESMO plano do Painel e do "Vai junto nesta corrida?": a casa sugere quem vai
// junto, com a cotação. Aceitar SOMA às corridas em edição, nunca apaga.
const dismissed = ref<string[]>([]);
const suggestions = computed(() =>
  visibleSuggestions((data.value?.ride_plan?.suggestions ?? []) as RideSuggestion[], editing.value, dismissed.value),
);
const headline = computed(() => suggestionsHeadline(suggestions.value));
const callAll = computed(() => callAllLabel(suggestions.value));
// As corridas que vieram de sugestões e esperam a confirmação no sheet.
const sheetNumbers = ref<number[]>([]);
function acceptSuggestions(list: RideSuggestion[], { call: withSheet }: { call: boolean }) {
  const rides = ridesFromSuggestions(list, freeNumbers.value, editing.value);
  if (!rides) {
    useSonner.info("Não há letras livres agora. Chame ou desfaça uma corrida antes.");
    return;
  }
  editing.value = [...editing.value, ...rides];
  active.value = rides[0]!.number;
  if (withSheet) sheetNumbers.value = rides.map((ride) => ride.number);
}
// "Voltar": as corridas da sugestão saem da edição; as que o operador já montava ficam.
function closeSheet() {
  const numbers = sheetNumbers.value;
  sheetNumbers.value = [];
  editing.value = editing.value.filter((ride) => !numbers.includes(ride.number));
  if (!editing.value.some((ride) => ride.number === active.value)) active.value = editing.value[0]?.number ?? 0;
}
async function confirmSheet() {
  const numbers = sheetNumbers.value;
  sheetNumbers.value = [];
  await call(numbers);
}
const suggestionOf = (refs: readonly string[]) =>
  (data.value?.ride_plan?.suggestions ?? []).find((item) => item.refs.join("|") === refs.join("|"));
const canAddRide = computed(
  () => waiting.value.length > 0 && nextFreeNumber(freeNumbers.value, editingNumbers.value) !== null && editing.value.every((ride) => ride.refs.length),
);

// ── cotação e ordem de cada corrida (P1-10, J03) ───────────────────────────
const quotes = useEditingQuotes(editing);
const stopsOf = (ride: EditingRide) =>
  ride.refs.map((ref) => byRef.value.get(ref)).filter((stop): stop is DeliveryStopProjection => Boolean(stop));
// A ordem que o entregador segue: a da cotação (o servidor já ordenou a rota),
// senão o espelho do `courier._route` aqui na tela. Nunca a ordem dos toques.
function routeOf(ride: EditingRide): DeliveryStopProjection[] {
  const stops = stopsOf(ride);
  const quoted = quotes.value[ride.number]?.quote?.stops;
  if (quoted && quoted.length === stops.length && stops.every((stop) => quoted.includes(stop.ref)))
    return quoted.map((ref) => stops.find((stop) => stop.ref === ref)!);
  return routeOrder(origin.value, stops);
}
const linesOf = (ride: EditingRide) => {
  const state = quotes.value[ride.number];
  return quoteLines(state?.quote ?? null, ride.refs.length, state?.failure ?? "");
};

// ── maquininha de cada corrida (P1-12) ──────────────────────────────────────
const machines = computed(() => data.value?.machines ?? []);
const freeMachineRefs = computed(() => machines.value.map((m) => String(m.ref)));
const machineItems = computed(() => machines.value.map((m) => ({ label: String(m.label), value: String(m.ref) })));
const needing = computed(() => ridesNeedingMachine(ready.value, waitingAll.value));
const machineChoice = ref<Record<number, string>>({});
const assigned = computed(() => assignMachines(needing.value, freeMachineRefs.value, machineChoice.value));
const shortfall = computed(() => machineShortfall(needing.value.length, freeMachineRefs.value.length));
function chooseMachine(number: number, value: string) {
  machineChoice.value = { ...assigned.value, [number]: value };
}
// "Juntar numa corrida só": as corridas de cartão viram uma, quando cabem.
const canJoinCardRides = computed(() => {
  const refs = needing.value.flatMap((number) => editing.value.find((ride) => ride.number === number)?.refs ?? []);
  return needing.value.length > 1 && refs.length <= maxStops.value;
});
function joinCardRides() {
  const [first, ...others] = needing.value;
  const target = editing.value.find((ride) => ride.number === first);
  if (!target) return;
  for (const number of others) {
    const ride = editing.value.find((item) => item.number === number);
    if (ride) target.refs = [...target.refs, ...ride.refs];
  }
  editing.value = editing.value.filter((ride) => !others.includes(ride.number));
  active.value = target.number;
}

// ── troco conferido ─────────────────────────────────────────────────────────
// O que o operador digitou, por pedido; sem mexer, vale o sugerido.
const change = ref<Record<string, string>>({});
const changeOf = (stop: DeliveryStopProjection) => changeValue(stop, change.value);
function setChange(ref: string, value: string | number) {
  change.value = { ...change.value, [ref]: String(value ?? "") };
}

// ── chamar, com balanço por corrida ─────────────────────────────────────────
const sending = ref(false);
// A chamada que parou tudo (sem rede, servidor fora): as que faltavam ficam para chamar.
const failure = ref("");
// Um aviso por corrida que não abriu, preso ao cartão dela (J08, J14).
const failures = ref<Record<number, RideFailure>>({});
watch(
  editing,
  (list) => {
    // A corrida mudou de pedidos (ou saiu): o aviso de antes já não é dela.
    const next: Record<number, RideFailure> = {};
    for (const ride of list) {
      const old = failures.value[ride.number];
      if (old && old.refs.join("|") === ride.refs.join("|")) next[ride.number] = old;
    }
    failures.value = next;
  },
  { deep: true },
);
function dismissFailure(number: number) {
  const { [number]: _gone, ...rest } = failures.value;
  failures.value = rest;
}
const callLabel = computed(() =>
  ready.value.length === 1 ? `Chamar a corrida ${rideLetter(ready.value[0]!.number)}` : `Chamar ${ready.value.length} corridas`,
);
const machineMissing = computed(() => needing.value.some((number) => !assigned.value[number]));
const canCall = computed(() => ready.value.length > 0 && !sending.value && !machineMissing.value);
const summary = computed(() =>
  callSummary(editingCount.value, ready.value.length, ready.value.map((ride) => quotes.value[ride.number]?.quote ?? null)),
);
const callAction = computed<OperatorActionBarAction>(() => ({
  label: callLabel.value,
  shortLabel: "Chamar",
  icon: "i-lucide-bike",
  loading: sending.value,
  disabled: !canCall.value,
  reason: machineMissing.value ? shortfall.value || "Escolha a maquininha de cada corrida." : "",
  onSelect: () => void call(),
}));
async function call(only?: number[]) {
  sending.value = true;
  failure.value = "";
  const targets = only ? ready.value.filter((ride) => only.includes(ride.number)) : ready.value;
  const calls = rideCalls(targets, waitingAll.value, assigned.value, change.value);
  const called: string[] = [];
  let opened = 0;
  // A corrida que já existia com os mesmos pedidos (chamada em outro dispositivo):
  // o servidor diz, e a frase é a dele.
  let already = "";
  for (const item of calls) {
    try {
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
      opened += 1;
    } catch (err) {
      const codes = item.refs.map((ref) => byRef.value.get(ref)?.code ?? ref);
      const detail = httpErrorMessage(err, "A chamada não chegou. Confira a internet deste dispositivo.");
      failures.value = {
        ...failures.value,
        [item.number]: { number: item.number, refs: item.refs, title: rideFailureTitle(item.number, codes), detail },
      };
      // Recusa do servidor é desta corrida: as outras seguem. Sem rede (ou servidor
      // fora), a próxima falharia igual: para, e as que faltavam ficam na edição.
      if (failureStops(httpError(err).status)) {
        const left = calls.length - opened - 1;
        failure.value = left > 0 ? `Parou na corrida ${rideLetter(item.number)}. ${left === 1 ? "A outra ficou" : `As outras ${left} ficaram`} para chamar.` : "";
        break;
      }
    }
  }
  if (opened)
    useSonner.success(
      opened === 1 && calls.length === 1
        ? already || "Corrida chamada. A TaOn avisa quando alguém aceitar."
        : `${opened} ${opened === 1 ? "corrida chamada" : "corridas chamadas"}.`,
    );
  const done = new Set(called);
  editing.value = editing.value.filter((ride) => !ride.refs.some((ref) => done.has(ref)));
  if (!editing.value.some((ride) => ride.number === active.value)) active.value = editing.value[0]?.number ?? 0;
  sending.value = false;
  await refresh();
}
// "Chamar separadas": a corrida que não abriu vira uma corrida por pedido, com o
// mesmo troco e as maquininhas redistribuídas, e só elas são chamadas.
function callSeparately(number: number) {
  const ride = editing.value.find((item) => item.number === number);
  if (!ride || ride.refs.length < 2) return;
  const taken = editing.value.filter((item) => item !== ride).map((item) => item.number);
  const numbers: number[] = [];
  for (const _ of ride.refs) {
    const next = nextFreeNumber(freeNumbers.value, [...taken, ...numbers]) ?? (numbers.length ? null : number);
    if (next === null) {
      useSonner.info("Não há letras livres para separar agora. Chame de novo juntas.");
      return;
    }
    numbers.push(next);
  }
  const singles = ride.refs.map((ref, k) => ({ number: numbers[k]!, refs: [ref] }));
  editing.value = [...editing.value.filter((item) => item !== ride), ...singles];
  dismissFailure(number);
  void nextTick(() => call(numbers));
}

// "Chamar de novo": a última chamada ficou sem resposta. O primeiro toque arma a
// confirmação com a frase do servidor (um toque nunca chama); o segundo libera a
// tentativa pendente e chama outra, a MESMA ação do Painel do pedido.
const armedAgain = ref("");
const againBusy = ref("");
async function dispatchAgain(stop: DeliveryStopProjection) {
  armedAgain.value = "";
  againBusy.value = stop.ref;
  try {
    await intentions.execute(stop.ref, "courier-dispatch-again", stop.dispatch_again_action ?? undefined, {});
    useSonner.success(`${stop.code}: chamada de novo. A TaOn avisa quando alguém aceitar.`);
  } catch (err) {
    useSonner.error(httpErrorMessage(err, "Não foi possível chamar de novo. Atualize e tente outra vez."));
  } finally {
    againBusy.value = "";
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
async function rideAction(ride: DeliveryRideProjection, operation: "courier-back" | "courier-cancel", reasonId?: number) {
  const action = operation === "courier-back" ? ride.back_action : ride.cancel_action;
  busyRide.value = ride.key;
  try {
    // Cancelar só chega aqui pela confirmação do detalhe (`CourierCancelConfirm`);
    // depois do aceite ela já traz o motivo, que vai à TaOn como `reason_id`.
    await intentions.execute(ride.lead_ref, operation, action ?? undefined, reasonId ? { reason_id: reasonId } : {});
    useSonner.success(operation === "courier-back" ? `Corrida ${ride.letter} encerrada.` : "Pedido de cancelamento enviado à TaOn.");
  } catch (err) {
    useSonner.error(httpErrorMessage(err, "Não foi possível. Atualize e tente de novo."));
  } finally {
    busyRide.value = "";
    await refresh();
  }
}
function cancelOpenRide(reasonId?: number) {
  if (openRide.value) void rideAction(openRide.value, "courier-cancel", reasonId);
}
// "Entregador voltou" fecha dinheiro, troco e maquininha: nunca num toque só. Abre a
// mesma conferência da Fila (`CourierBackDialog`); "Voltou diferente" leva ao pedido,
// onde mora o acerto à mão.
const backRide = ref<DeliveryRideProjection | null>(null);
const backCard = computed(() => (backRide.value ? backCheck(backRide.value) : null));
async function confirmBack() {
  const ride = backRide.value;
  if (!ride) return;
  await rideAction(ride, "courier-back");
  backRide.value = null;
}
function backDifferent() {
  const ride = backRide.value;
  backRide.value = null;
  if (ride) void navigateTo(`/${encodeURIComponent(ride.lead_ref)}`);
}

// ── mapa ────────────────────────────────────────────────────────────────────
type Located = DeliveryStopProjection & { latitude: number; longitude: number };
const located = (stop: DeliveryStopProjection): stop is Located =>
  stop.latitude !== null && stop.longitude !== null;
const mapWaiting = computed<MapPoint[]>(() =>
  waiting.value.filter(located).map((stop) => ({ ...stop, preparing: stop.stage !== "Pronto" })),
);
const mapBuilding = computed(() =>
  // Na ordem da rota, como a lista: o "1" do mapa é o "1" do cartão.
  editing.value.map((ride) => ({ number: ride.number, stops: routeOf(ride).filter(located) })),
);
const mapLive = computed<MapLiveRide[]>(() =>
  rides.value.map((ride) => ({ number: ride.number, stops: ride.stops.filter(located), courier: ride.position })),
);
// A loja sem coordenada NÃO vira o primeiro cliente (o ícone da loja ia parar na casa
// dele): o mapa desenha só o que tem lugar, e a rota começa na primeira parada.
const origin = computed(() => data.value?.origin ?? null);
const hasMap = computed(
  () => Boolean(origin.value) || mapWaiting.value.length > 0 || mapLive.value.some((ride) => ride.stops.length > 0),
);
const unlocated = computed(() => waitingAll.value.filter((stop) => !located(stop)).length);
const editingCount = computed(() => ready.value.reduce((sum, ride) => sum + ride.refs.length, 0));

// ── o sheet de chamar ──────────────────────────────────────────────────────
const sheetRides = computed<CallSheetRide[]>(() =>
  sheetNumbers.value
    .map((number) => editing.value.find((ride) => ride.number === number))
    .filter((ride): ride is EditingRide => Boolean(ride))
    .map((ride) => {
      const stops = routeOf(ride);
      const plan = suggestionOf(ride.refs) ?? suggestionOf(stops.map((stop) => stop.ref));
      const live = linesOf(ride);
      return {
        number: ride.number,
        letter: rideLetter(ride.number),
        color: rideColor(ride.number - 1),
        stops: stops.map((stop) => ({
          ref: stop.ref, code: stop.code, customer: stop.customer, place: stop.place,
          change_out_suggested_q: stop.change_out_suggested_q, change: changeOf(stop),
        })),
        // A cotação viva da corrida (a mesma que a chamada vai abrir); enquanto ela
        // não chega, a do plano.
        lines: live.length ? live : plan ? suggestionQuoteLines(plan as RideSuggestion) : [],
        order: suggestionOrder(stops.map((stop) => stop.code)),
        late: plan ? suggestionLate(plan) : "",
        needsMachine: needing.value.includes(ride.number),
        machine: assigned.value[ride.number] ?? "",
      };
    }),
);
const sheetTitle = computed(() =>
  sheetRides.value.length === 1 ? `Chamar a corrida ${sheetRides.value[0]!.letter}` : `Chamar ${sheetRides.value.length} corridas`,
);
const sheetLines = computed(() => {
  const list = sheetRides.value
    .map((ride) => suggestionOf(editing.value.find((item) => item.number === ride.number)?.refs ?? []))
    .filter(Boolean) as RideSuggestion[];
  return list.length === sheetRides.value.length ? suggestionsHeadline(list).lines : [];
});
const sheetMachineMissing = computed(() => sheetRides.value.some((ride) => ride.needsMachine && !ride.machine));
const sheetCallLabel = computed(() =>
  sheetRides.value.length === 1 ? `Chamar a corrida ${sheetRides.value[0]!.letter}` : `Chamar as ${sheetRides.value.length} corridas`,
);
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
          v-if="hasMap"
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
            <!-- As sugestões da casa (ride_plan): cotadas, já dizem quanto economiza e
                 quem chega depois; sem cotação, só a montagem à mão. -->
            <div v-if="suggestions.length" class="mt-2 rounded-xl bg-elevated/60 p-3" data-ride-suggestions>
              <div class="flex items-start gap-2">
                <NuxtIcon name="i-lucide-sparkles" class="mt-0.5 size-4 shrink-0 text-muted" />
                <div class="min-w-0 flex-1">
                  <p class="op-body font-medium text-highlighted">{{ headline.title }}</p>
                  <p
                    v-for="line in headline.lines"
                    :key="line.text"
                    class="op-body tabular-nums [font-variant-emoji:text]"
                    :class="line.strong ? 'font-medium text-highlighted' : 'text-muted'"
                  >
                    {{ line.text }}
                  </p>
                </div>
              </div>
              <ul class="mt-2 flex flex-col divide-y divide-default">
                <li v-for="s in suggestions" :key="s.key" class="flex flex-col gap-2 py-2 sm:flex-row sm:items-center" data-ride-suggestion>
                  <div class="min-w-0 flex-1">
                    <p class="op-body"><span class="font-medium text-highlighted">{{ s.codes.join(" + ") }}</span> <span v-if="s.places" class="text-muted">· {{ s.places }}</span></p>
                    <template v-if="s.quoted">
                      <p
                        v-for="line in suggestionQuoteLines(s)"
                        :key="line.text"
                        class="op-micro tabular-nums [font-variant-emoji:text]"
                        :class="line.strong ? 'font-medium text-highlighted' : 'text-muted'"
                      >
                        {{ line.text }}
                      </p>
                      <p v-if="suggestionLate(s)" class="op-micro text-muted">{{ suggestionLate(s) }}</p>
                    </template>
                    <p v-else class="op-micro text-warning">A TaOn não cotou agora. Monte a corrida se quiser levar junto.</p>
                  </div>
                  <div class="flex shrink-0 flex-wrap gap-2">
                    <NuxtButton v-if="s.suggested" class="min-h-11" color="neutral" variant="outline" icon="i-lucide-bike" label="Chamar juntas" data-ride-suggestion-call @click="acceptSuggestions([s], { call: true })" />
                    <NuxtButton v-else class="min-h-11" color="neutral" variant="outline" icon="i-lucide-route" label="Montar a corrida" data-ride-suggestion-build @click="acceptSuggestions([s], { call: false })" />
                    <NuxtButton class="min-h-11" color="neutral" variant="ghost" label="Agora não" @click="dismissed = [...dismissed, s.key]" />
                  </div>
                </li>
              </ul>
              <NuxtButton v-if="callAll" block class="mt-2 min-h-11" icon="i-lucide-bike" :label="callAll" data-ride-suggestions-call-all @click="acceptSuggestions(suggestions, { call: true })" />
            </div>
            <ul class="mt-2 flex flex-col">
              <li v-for="stop in waiting" :key="stop.ref">
                <!-- Chamada sem resposta: a linha não entra em corrida; o gesto é conferir e chamar de novo. -->
                <div v-if="stop.dispatch_again_action" class="flex flex-col gap-2 rounded-lg bg-elevated/60 px-2 py-2" data-waiting-again>
                  <div class="flex items-center gap-2.5">
                    <span class="grid size-6 shrink-0 place-items-center rounded-full bg-warning/15 text-warning"><NuxtIcon name="i-lucide-circle-help" class="size-3.5" /></span>
                    <span class="min-w-0 flex-1">
                      <span class="block truncate op-body"><span class="font-medium text-highlighted">{{ stop.code }} · {{ stop.customer }}</span> <span class="text-muted">· {{ stop.place }}</span></span>
                      <!-- Armado, a confirmação embaixo já diz o que aconteceu e o que conferir. -->
                      <span v-if="armedAgain !== stop.ref" class="block op-micro text-toned">{{ stop.error }}</span>
                    </span>
                    <NuxtButton v-if="armedAgain !== stop.ref" color="neutral" variant="outline" icon="i-lucide-rotate-cw" :label="stop.dispatch_again_action.label" :disabled="!stop.dispatch_again_action.enabled" :title="stop.dispatch_again_action.reason || undefined" @click="armedAgain = stop.ref" />
                  </div>
                  <div v-if="armedAgain === stop.ref" class="flex flex-wrap items-center gap-2 pl-8.5" data-waiting-again-confirm>
                    <p class="min-w-0 flex-1 op-micro text-toned">{{ (stop.dispatch_again_action.confirmation as { description?: string })?.description }}</p>
                    <NuxtButton color="neutral" variant="ghost" label="Agora não" @click="armedAgain = ''" />
                    <NuxtButton color="primary" icon="i-lucide-rotate-cw" :label="`Chamar ${stop.code} de novo`" :loading="againBusy === stop.ref" @click="dispatchAgain(stop)" />
                  </div>
                </div>
                <div v-else-if="stop.group_refusal" class="flex items-center gap-2.5 px-2 py-2" data-waiting-refused>
                  <span class="grid size-6 shrink-0 place-items-center rounded-full border-2 border-dashed border-default text-dimmed"><NuxtIcon name="i-lucide-minus" class="size-3.5" /></span>
                  <span class="min-w-0 flex-1">
                    <span class="block truncate op-body"><span class="font-medium text-highlighted">{{ stop.code }} · {{ stop.customer }}</span> <span class="text-muted">· {{ stop.place }}</span></span>
                    <span class="block op-micro text-toned">{{ stop.group_refusal }}</span>
                  </span>
                </div>
                <NuxtButton v-else color="neutral" variant="ghost" block class="justify-start gap-2.5 text-left" @click="toggle(stop.ref)">
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
                    <span class="op-micro tabular-nums text-muted" data-ride-capacity>{{ ride.refs.length }} {{ ride.refs.length === 1 ? "pedido" : "pedidos" }} (cabem até {{ maxStops }})</span>
                    <span v-if="ride.number !== active && ride.refs.length" class="ml-1 min-w-0 flex-1 truncate op-micro text-muted">{{ routeOf(ride).map((stop) => stop.code).join(" → ") }}</span>
                  </NuxtButton>
                  <NuxtButton icon="i-lucide-trash-2" color="neutral" variant="ghost" square class="size-11 justify-center" :aria-label="`Desfazer a corrida ${rideLetter(ride.number)}`" @click="drop(ride.number)" />
                </div>
                <!-- A corrida que não abriu: o aviso é DELA, com o gesto para sair do lugar. -->
                <NuxtAlert
                  v-if="failures[ride.number]"
                  class="mx-3 mb-2"
                  color="error"
                  variant="subtle"
                  icon="i-lucide-circle-alert"
                  :title="failures[ride.number]!.title"
                  :description="failures[ride.number]!.detail"
                  close
                  :actions="alertActions('error', [
                    { label: 'Chamar de novo', icon: 'i-lucide-rotate-cw', disabled: sending, onClick: () => call([ride.number]) },
                    ride.refs.length > 1 && { label: 'Chamar separadas', disabled: sending, onClick: () => callSeparately(ride.number) },
                  ])"
                  data-ride-failure
                  @update:open="(value: boolean) => { if (!value) dismissFailure(ride.number); }"
                />
                <ol v-if="ride.number === active" class="flex flex-col gap-1 px-3 pb-2">
                  <li v-if="!ride.refs.length" class="rounded-lg border border-dashed border-default px-3 py-3 text-center op-body text-muted">Toque nos pedidos no mapa ou na lista.</li>
                  <li v-for="(stop, k) in routeOf(ride)" :key="stop.ref" class="flex items-start gap-2.5 rounded-lg bg-elevated/60 px-2 py-1.5">
                    <span class="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border-[3px] border-dotted bg-white op-micro font-bold" :style="{ borderColor: rideColor(ride.number - 1).bg, color: PIN_TEXT }">{{ k + 1 }}</span>
                    <span class="min-w-0 flex-1">
                      <span class="block op-body font-medium text-highlighted">{{ stop.code }} · {{ stop.customer }}</span>
                      <span class="block op-micro text-muted">{{ [stop.place, stop.stage !== "Pronto" ? stop.stage : ""].filter(Boolean).join(" · ") }}</span>
                      <!-- Troco: o operador confere e corrige antes de chamar; o R$ fica dentro do campo. -->
                      <label v-if="stop.change_out_suggested_q > 0" class="mt-1 flex items-center gap-2" data-ride-change>
                        <span class="op-micro text-toned">Troco</span>
                        <NuxtInput
                          :model-value="changeOf(stop)"
                          inputmode="decimal"
                          size="sm"
                          class="w-28"
                          :aria-label="`Troco para ${stop.code}`"
                          @update:model-value="(value: string | number) => setChange(stop.ref, value)"
                        >
                          <template #leading><span class="op-micro text-muted">R$</span></template>
                        </NuxtInput>
                      </label>
                    </span>
                    <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square class="size-11 justify-center" :aria-label="`Tirar ${stop.code}`" @click="toggle(stop.ref)" />
                  </li>
                  <li v-if="ride.refs.length > 1" class="px-1 pt-1 op-micro text-muted">O entregador sai da loja e segue esta ordem.</li>
                </ol>
                <!-- Cotação (duas linhas, ✔ na mais barata) e a maquininha DESTA corrida. -->
                <div v-if="ride.refs.length" class="flex flex-col gap-1.5 px-3 pb-3" data-ride-quote>
                  <p v-if="quotes[ride.number]?.pending" class="op-micro text-muted">Cotando na TaOn…</p>
                  <p
                    v-for="line in linesOf(ride)"
                    :key="line.text"
                    class="op-body tabular-nums [font-variant-emoji:text]"
                    :class="line.strong ? 'font-medium text-highlighted' : 'text-muted'"
                  >
                    {{ line.text }}
                  </p>
                  <div v-if="needing.includes(ride.number)" class="flex flex-wrap items-center gap-2" data-ride-machine>
                    <span class="op-body text-toned">Maquininha:</span>
                    <NuxtSelect
                      v-if="machineItems.length"
                      :model-value="assigned[ride.number] || undefined"
                      :items="machineItems"
                      placeholder="Escolha"
                      class="min-w-40"
                      :aria-label="`Maquininha da corrida ${rideLetter(ride.number)}`"
                      @update:model-value="(value: string) => chooseMachine(ride.number, value)"
                    />
                    <span v-if="!assigned[ride.number]" class="op-body text-warning">Nenhuma livre</span>
                  </div>
                </div>
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
                @back="backRide = ride"
              />
            </div>
          </section>
        </div>

        <div v-if="ready.length" class="flex flex-col gap-2 border-t border-default bg-default p-4">
          <p v-if="failure" class="op-body text-error" aria-live="assertive">{{ failure }}</p>
          <div v-if="shortfall" class="flex flex-wrap items-center gap-2" data-machine-shortfall>
            <p class="min-w-0 flex-1 op-body text-warning">{{ shortfall }}</p>
            <NuxtButton v-if="canJoinCardRides" color="neutral" variant="outline" icon="i-lucide-merge" label="Juntar numa corrida só" @click="joinCardRides" />
          </div>
          <div class="flex items-center gap-3">
            <p class="min-w-0 flex-1 op-body text-muted">
              {{ summary }}<template v-if="waiting.length"> · {{ waiting.length }} {{ waiting.length === 1 ? "fica" : "ficam" }}</template>
            </p>
            <NuxtButton class="hidden lg:inline-flex" icon="i-lucide-bike" :label="callLabel" :loading="sending" :disabled="!canCall" @click="call()" />
          </div>
        </div>
      </div>
    </div>

    <!-- No celular, o "Chamar" é a ação do momento na base (kit). -->
    <OperatorActionBar v-if="ready.length" :action="callAction" :context-label="summary" label="Chamar as corridas" />

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
          @back="backRide = openRide"
          @cancel="cancelOpenRide"
        />
      </template>
    </NuxtSlideover>

    <!-- A sugestão aceita: confere e chama no mesmo sheet (desenho do juiz, F5). -->
    <CourierCallSheet
      :open="sheetRides.length > 0"
      :title="sheetTitle"
      :lines="sheetLines"
      :rides="sheetRides"
      :machine-items="machineItems"
      :call-label="sheetCallLabel"
      :can-call="!sending && !sheetMachineMissing"
      :reason="sheetMachineMissing ? shortfall || 'Escolha a maquininha de cada corrida.' : ''"
      :busy="sending"
      @close="closeSheet"
      @confirm="confirmSheet"
      @change="setChange"
      @machine="chooseMachine"
    />

    <!-- Entregador voltou: confere e só então encerra a corrida inteira. -->
    <CourierBackDialog
      :card="backCard"
      :busy="Boolean(backRide && busyRide === backRide.key)"
      @confirm="confirmBack"
      @different="backDifferent"
      @close="backRide = null"
    />
  </main>
</template>
