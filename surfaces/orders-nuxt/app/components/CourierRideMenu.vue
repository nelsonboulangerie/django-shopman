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

const props = defineProps<{ choices: RideChoice[] }>();
// PRÉVIA (14/11): três desenhos do modal por ?ride=A|B|C. Sai antes do merge.
const route = useRoute();
const layout = computed(() => String(route.query.ride || "A"));
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

// A lista é uma escolha múltipla com teto: o que passa do teto fica inerte.
const items = computed(() =>
  props.choices.map((choice) => ({
    value: choice.card.ref,
    label: choice.label,
    description: rideOfferLine(choice),
    disabled: !picked.value.includes(choice.card.ref) && picked.value.length >= MAX_RIDE_STOPS,
  })),
);
// Por bairro (B): quem junta olha o bairro primeiro.
const byPlace = computed(() => {
  const groups = new Map<string, typeof items.value>();
  props.choices.forEach((choice, index) => {
    const key = choice.place || "Sem bairro";
    groups.set(key, [...(groups.get(key) || []), { ...items.value[index]!, description: [choice.stage, choice.distance_label, choice.needs_machine ? "leva a maquininha" : choice.change_out_suggested_q > 0 ? "leva troco" : ""].filter(Boolean).join(" · ") }]);
  });
  return [...groups.entries()].map(([place, rows]) => ({ place, rows }));
});
function setPicked(next: unknown) {
  picked.value = [...new Set(Array.isArray(next) ? next.map(String) : [])].slice(0, MAX_RIDE_STOPS);
}
const pickedCount = computed(() => `${picked.value.length} de ${MAX_RIDE_STOPS}`);
const stops = computed(() => chosen.value);
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
    :ui="{
      content: layout === 'C' ? 'sm:max-w-3xl' : 'sm:max-w-lg',
      body: layout === 'C' ? 'p-0 sm:p-0 overflow-hidden' : undefined,
      footer: 'flex-col items-stretch gap-3 sm:flex-row sm:flex-wrap sm:items-center',
    }"
    data-courier-ride-panel
  >
    <template #body>
      <!-- A: cartões selecionáveis, um por pedido -->
      <NuxtCheckboxGroup
        v-if="layout === 'A'"
        :model-value="picked"
        :items="items"
        variant="card"
        legend="Pedidos prontos para sair"
        :ui="{ legend: 'sr-only', fieldset: 'gap-2' }"
        data-courier-ride-orders
        @update:model-value="setPicked"
      />

      <!-- B: por bairro, linhas enxutas -->
      <div v-else-if="layout === 'B'" class="flex flex-col gap-4" data-courier-ride-orders>
        <section v-for="group in byPlace" :key="group.place" class="flex flex-col gap-1.5">
          <h3 class="flex items-center gap-2 op-label font-semibold text-highlighted">
            <NuxtIcon name="i-lucide-map-pin" class="size-4 text-muted" />
            {{ group.place }}
            <NuxtBadge :label="String(group.rows.length)" color="neutral" variant="soft" size="sm" />
          </h3>
          <NuxtCheckboxGroup
            :model-value="picked"
            :items="group.rows"
            variant="table"
            :legend="group.place"
            :ui="{ legend: 'sr-only' }"
            @update:model-value="(v) => setPicked([...picked.filter((r) => !group.rows.some((row) => row.value === r)), ...(Array.isArray(v) ? v : [])])"
          />
        </section>
      </div>

      <!-- C: a lista à esquerda, a corrida montando à direita -->
      <div v-else class="grid h-[min(70dvh,40rem)] min-h-0 sm:grid-cols-[1fr_17rem]" data-courier-ride-orders>
        <div class="min-h-0 overflow-y-auto p-4">
          <NuxtCheckboxGroup
            :model-value="picked"
            :items="items"
            variant="card"
            legend="Pedidos prontos para sair"
            :ui="{ legend: 'sr-only', fieldset: 'gap-2' }"
            @update:model-value="setPicked"
          />
        </div>
        <aside class="flex min-h-0 flex-col gap-3 overflow-y-auto border-t border-default bg-elevated/50 p-4 sm:border-t-0 sm:border-l">
          <p class="op-label font-semibold text-highlighted">A corrida <span class="font-normal text-muted">· {{ pickedCount }}</span></p>
          <p v-if="!stops.length" class="op-body text-muted">Marque os pedidos que vão juntos.</p>
          <ol v-else class="flex flex-col gap-2">
            <li v-for="(stop, index) in stops" :key="stop.card.ref" class="flex items-start gap-2">
              <span class="grid size-6 shrink-0 place-items-center rounded-full bg-primary op-micro font-semibold text-inverted">{{ index + 1 }}</span>
              <span class="min-w-0"><span class="block truncate op-body font-medium">{{ stop.label }}</span><span class="block truncate op-micro text-muted">{{ stop.place }}</span></span>
            </li>
          </ol>
          <p v-if="quoteLine" class="op-body font-medium tabular-nums" role="status" data-courier-ride-quote>{{ quoteLine }}</p>
          <NuxtFormField
            v-for="choice in asksChange"
            :key="`change-${choice.card.ref}`"
            :label="`Troco do ${code(choice.card.ref)}`"
            :description="choice.change_label || undefined"
            data-courier-ride-change
          >
            <NuxtInput v-model="changeOut[choice.card.ref]" class="w-full" type="text" inputmode="decimal" icon="i-lucide-circle-dollar-sign" :aria-label="`Troco que o entregador leva no pedido ${code(choice.card.ref)}`" />
          </NuxtFormField>
          <div v-if="needsMachine && free.length >= 2" class="flex flex-col gap-1.5" data-courier-ride-machine>
            <p class="op-body font-medium">Qual maquininha vai?</p>
            <div class="grid grid-cols-2 gap-2">
              <NuxtButton v-for="opt in free" :key="opt.ref" type="button" :label="opt.label" :color="machineRef === opt.ref ? 'primary' : 'neutral'" :variant="machineRef === opt.ref ? 'solid' : 'outline'" @click="machineRef = opt.ref" />
            </div>
          </div>
          <p v-else-if="needsMachine && !free.length" class="op-body" data-courier-ride-no-machine>
            {{ machinesOutSentence(machines) }} Tire da corrida o pedido de cartão ou espere a maquininha voltar.
          </p>
          <NuxtAlert v-if="failure" color="error" variant="subtle" :description="failure" data-courier-ride-error />
          <NuxtButton class="sticky bottom-0 mt-auto" block icon="i-lucide-bike" :label="`Chamar a corrida (${picked.length})`" :loading="sending" :disabled="!canCall" data-courier-ride-call @click="call" />
        </aside>
      </div>

    </template>

    <template v-if="layout !== 'C'" #footer>
      <!-- A e B: o que a corrida pede, no pé, junto do botão: nunca escondido na lista -->
      <div v-if="layout !== 'C' && (asksChange.length || needsMachine)" class="flex w-full flex-col gap-3 sm:basis-full">
        <NuxtFormField
          v-for="choice in asksChange"
          :key="`change-${choice.card.ref}`"
          :label="`Troco do pedido ${code(choice.card.ref)}`"
          :description="choice.change_label || undefined"
          data-courier-ride-change
        >
          <NuxtInput v-model="changeOut[choice.card.ref]" class="w-full" type="text" inputmode="decimal" icon="i-lucide-circle-dollar-sign" :aria-label="`Troco que o entregador leva no pedido ${code(choice.card.ref)}`" />
        </NuxtFormField>
        <div v-if="needsMachine && free.length >= 2" class="flex flex-col gap-1.5" data-courier-ride-machine>
          <p class="op-body font-medium">Qual maquininha vai na corrida?</p>
          <div class="grid grid-cols-2 gap-2">
            <NuxtButton v-for="opt in free" :key="opt.ref" type="button" :label="opt.label" :color="machineRef === opt.ref ? 'primary' : 'neutral'" :variant="machineRef === opt.ref ? 'solid' : 'outline'" @click="machineRef = opt.ref" />
          </div>
        </div>
        <p v-else-if="needsMachine && !free.length" class="op-body" data-courier-ride-no-machine>
          {{ machinesOutSentence(machines) }} Tire da corrida o pedido de cartão ou espere a maquininha voltar.
        </p>
      </div>
      <NuxtAlert v-if="failure" color="error" variant="subtle" :description="failure" data-courier-ride-error />
      <p class="min-w-0 flex-1 op-body tabular-nums" :class="quoteLine ? 'font-medium' : 'text-muted'" role="status" data-courier-ride-quote>
        {{ quoteLine || `${pickedCount} marcados` }}
      </p>
      <NuxtButton icon="i-lucide-bike" :label="`Chamar a corrida (${picked.length})`" :loading="sending" :disabled="!canCall" data-courier-ride-call @click="call" />
    </template>
  </NuxtModal>
</template>
