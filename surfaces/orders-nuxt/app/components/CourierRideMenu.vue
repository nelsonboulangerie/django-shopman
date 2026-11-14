<script setup lang="ts">
// Uma corrida da TaOn para várias entregas prontas: o botão do cabeçalho aparece
// com duas ou mais que podem ir juntas (`ride_candidates`) e abre a escolha. A
// TaOn leva os pedidos numa solicitação só, na ordem do percurso; o custo é da
// casa e o frete do cliente não muda. A corrida é uma saída: o troco sai da
// gaveta pedido a pedido e a maquininha é uma só para todos os pedidos de
// cartão (o "Voltou" fecha todos). A recusa do servidor aparece aqui mesmo.
import {
  courierRideBody,
  courierRideCallLabel,
  courierRideLabel,
  rideOfferLine,
  machinesOutSentence,
  MAX_RIDE_STOPS,
  rideChangeDefaults,
  splitRef,
  type RideChoice,
} from "~/presentation/board";
import { freeMachines } from "../../../operator-kit/app/presentation/custody";
import { useRideQuote } from "~/composables/useRideQuote";

type MappedChoice = RideChoice & { latitude?: number | null; longitude?: number | null };
const props = defineProps<{
  choices: MappedChoice[];
  origin?: { latitude: number; longitude: number } | null;
}>();
// PRÉVIA (14/11): desenhos do modal por ?ride=D|E|F. Sai antes do merge.
const route = useRoute();
const layout = computed(() => String(route.query.ride || "D"));
const emit = defineEmits<{ done: [] }>();

const open = ref(false);
const picked = ref<string[]>([]);
const changeOut = ref<Record<string, string>>({});
const machineRef = ref<string | undefined>();
const sending = ref(false);
const failure = ref("");

watch(open, (isOpen) => {
  if (!isOpen) return;
  failure.value = "";
  // Nada vem marcado: juntar é escolha do operador, que vê os bairros. Marcar
  // tudo mandaria numa corrida só entregas de lados opostos da cidade.
  picked.value = [];
  changeOut.value = rideChangeDefaults(props.choices);
  machineRef.value = undefined;
});

// A cotação da corrida com as entregas marcadas (a mesma que a chamada vai abrir).
const pickedRefs = computed(() => (open.value ? [...picked.value] : []));
const rideQuote = useRideQuote(pickedRefs);
const quoteLine = computed(() => {
  if (picked.value.length < 2) return "";
  if (rideQuote.pending.value) return "Cotando a corrida…";
  const quote = rideQuote.quote.value;
  return quote
    ? `Cotação: ${quote.display}. Ordem: ${quote.route}.`
    : rideQuote.failure.value;
});

const chosen = computed(() =>
  props.choices.filter((choice) => picked.value.includes(choice.card.ref)),
);
// As paradas na ordem em que o operador marcou.
const chosenInOrder = computed(() =>
  picked.value
    .map((ref) => props.choices.find((choice) => choice.card.ref === ref))
    .filter((choice): choice is MappedChoice => Boolean(choice)),
);
const asksChange = computed(() =>
  chosen.value.filter((choice) => choice.change_out_suggested_q > 0),
);
// As maquininhas do canal, como o despacho lê: do card de cartão escolhido.
const machineCard = computed(
  () => chosen.value.find((choice) => choice.needs_machine)?.card ?? null,
);
const needsMachine = computed(() => machineCard.value !== null);
const machines = computed(() => machineCard.value?.equipment_options ?? []);
const free = computed(() => freeMachines(machines.value));
// Uma livre: vai ela. Duas ou mais: o operador escolhe pela cor.
const machine = computed(() =>
  !needsMachine.value
    ? undefined
    : free.value.length === 1
      ? free.value[0]
      : free.value.find((opt) => opt.ref === machineRef.value),
);
const canCall = computed(
  () => picked.value.length >= 2 && (!needsMachine.value || !!machine.value),
);

function toggle(ref_: string, on: boolean) {
  picked.value = on
    ? [...picked.value, ref_].slice(0, MAX_RIDE_STOPS)
    : picked.value.filter((item) => item !== ref_);
}

async function call() {
  sending.value = true;
  failure.value = "";
  try {
    await $fetch("/api/v1/backstage/orders/courier-ride/", {
      method: "POST",
      body: courierRideBody(
        picked.value,
        props.choices,
        changeOut.value,
        machine.value?.ref,
      ),
    });
    open.value = false;
    emit("done");
  } catch (error) {
    failure.value = httpErrorMessage(
      error,
      "Não foi possível chamar a corrida. Atualize a fila.",
    );
  } finally {
    sending.value = false;
  }
}
const code = (ref_: string) => splitRef(ref_).code;

// Os bairros, na ordem em que aparecem; cada linha é uma escolha com teto.
const groups = computed(() => {
  const map = new Map<string, MappedChoice[]>();
  for (const choice of props.choices) {
    const key = choice.place || "Sem bairro";
    map.set(key, [...(map.get(key) || []), choice]);
  }
  return [...map.entries()].map(([place, rows]) => ({
    place,
    rows,
    items: rows.map((choice) => ({
      value: choice.card.ref,
      label: choice.label,
      description: [choice.stage, choice.distance_label, choice.needs_machine ? "leva a maquininha" : choice.change_out_suggested_q > 0 ? "leva troco" : ""].filter(Boolean).join(" · "),
      disabled: !picked.value.includes(choice.card.ref) && picked.value.length >= MAX_RIDE_STOPS,
    })),
  }));
});
function setPicked(next: unknown) {
  picked.value = [...new Set(Array.isArray(next) ? next.map(String) : [])].slice(0, MAX_RIDE_STOPS);
}
function setGroup(rows: MappedChoice[], next: unknown) {
  const mine = new Set(rows.map((row) => row.card.ref));
  const wanted = new Set(Array.isArray(next) ? next.map(String) : []);
  const kept = picked.value.filter((ref) => !mine.has(ref) || wanted.has(ref));
  setPicked([...kept, ...[...wanted].filter((ref) => !picked.value.includes(ref))]);
}
function flip(ref: string) {
  toggle(ref, !picked.value.includes(ref));
}
const groupPicked = (rows: MappedChoice[]) => rows.filter((row) => picked.value.includes(row.card.ref)).length;
// Marcar o bairro: troca a corrida pelos pedidos dele (até o teto).
function pickPlace(rows: MappedChoice[]) {
  setPicked(rows.map((row) => row.card.ref));
}
// As sugestões (F): o bairro com dois ou mais é uma corrida pronta.
const suggestions = computed(() => groups.value.filter((group) => group.rows.length >= 2));
const points = computed(() =>
  props.choices
    .filter((choice) => choice.latitude != null && choice.longitude != null)
    .map((choice) => ({
      ref: choice.card.ref,
      code: code(choice.card.ref),
      place: choice.place,
      latitude: Number(choice.latitude),
      longitude: Number(choice.longitude),
    })),
);
</script>

<template>
  <NuxtButton
    v-if="props.choices.length >= 2"
    icon="i-lucide-route"
    label="Juntar entregas"
    color="neutral"
    variant="outline"
    data-courier-ride-menu
    @click="open = true"
  />
  <NuxtModal
    v-model:open="open"
    title="Juntar entregas"
    :description="`Uma corrida da TaOn leva até ${MAX_RIDE_STOPS} pedidos, na ordem do percurso. O frete do cliente não muda.`"
    :ui="{ content: layout === 'E' ? 'sm:max-w-6xl' : 'sm:max-w-4xl', body: 'p-0 sm:p-0 overflow-hidden' }"
    data-courier-ride-panel
  >
    <template #body>
      <div
        class="grid h-[min(72dvh,44rem)] min-h-0"
        :class="layout === 'E' ? 'sm:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)_18rem]' : 'sm:grid-cols-[minmax(0,1fr)_19rem]'"
        data-courier-ride-orders
      >
        <!-- E: o mapa primeiro; tocar no ponto marca o pedido -->
        <div v-if="layout === 'E'" class="min-h-0 p-4 max-sm:hidden">
          <CourierRideMap :points="points" :picked="picked" :origin="origin" full @toggle="flip" />
        </div>

        <!-- a lista por bairro -->
        <div class="min-h-0 overflow-y-auto p-4" :class="layout === 'E' ? 'border-default sm:border-l' : ''">
          <!-- F: o bairro com dois ou mais vira uma corrida pronta, num toque -->
          <div v-if="layout === 'F' && suggestions.length" class="mb-4 flex flex-col gap-2" data-courier-ride-suggestions>
            <p class="op-micro font-semibold uppercase tracking-wide text-muted">Juntos por bairro</p>
            <div class="flex flex-wrap gap-2">
              <NuxtButton
                v-for="group in suggestions"
                :key="`s-${group.place}`"
                :label="group.place"
                icon="i-lucide-map-pin"
                :color="groupPicked(group.rows) === Math.min(group.rows.length, MAX_RIDE_STOPS) && picked.length === groupPicked(group.rows) ? 'primary' : 'neutral'"
                :variant="groupPicked(group.rows) === Math.min(group.rows.length, MAX_RIDE_STOPS) && picked.length === groupPicked(group.rows) ? 'solid' : 'outline'"
                @click="pickPlace(group.rows)"
              >
                <template #trailing>
                  <NuxtBadge :label="String(group.rows.length)" color="neutral" variant="soft" size="sm" />
                </template>
              </NuxtButton>
            </div>
          </div>

          <section v-for="group in groups" :key="group.place" class="mb-4 flex flex-col gap-1.5 last:mb-0">
            <div class="flex items-center gap-2">
              <NuxtIcon name="i-lucide-map-pin" class="size-4 shrink-0 text-muted" />
              <h3 class="min-w-0 flex-1 truncate op-label font-semibold text-highlighted">{{ group.place }}</h3>
              <span class="op-micro tabular-nums text-muted">{{ groupPicked(group.rows) ? `${groupPicked(group.rows)} de ${group.rows.length}` : group.rows.length }}</span>
              <NuxtButton
                v-if="layout === 'D' && group.rows.length >= 2"
                label="Marcar o bairro"
                color="neutral"
                variant="link"
                size="xs"
                @click="pickPlace(group.rows)"
              />
            </div>
            <NuxtCheckboxGroup
              :model-value="picked.filter((ref) => group.rows.some((row) => row.card.ref === ref))"
              :items="group.items"
              variant="table"
              :legend="group.place"
              :ui="{ legend: 'sr-only' }"
              @update:model-value="(v) => setGroup(group.rows, v)"
            />
          </section>
        </div>

        <!-- a corrida montando, com o botão sempre à vista -->
        <div class="min-h-0 border-t border-default bg-elevated/40 sm:border-t-0 sm:border-l">
          <CourierRideSummary
            v-model:change-out="changeOut"
            v-model:machine-ref="machineRef"
            :stops="chosenInOrder"
            :asks-change="asksChange"
            :needs-machine="needsMachine"
            :free="free"
            :machines="machines"
            :quote-line="quoteLine"
            :failure="failure"
            :sending="sending"
            :can-call="canCall"
            :timeline="layout !== 'D'"
            @remove="(ref) => toggle(ref, false)"
            @call="call"
          />
        </div>
      </div>
    </template>
  </NuxtModal>
</template>
