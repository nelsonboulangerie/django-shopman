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
</script>

<template>
  <NuxtPopover
    v-if="props.choices.length >= 2"
    v-model:open="open"
    :content="{ align: 'end' }"
  >
    <NuxtButton
      icon="i-lucide-route"
      label="Juntar entregas"
      color="neutral"
      variant="outline"
      data-courier-ride-menu
    />
    <template #content>
      <div class="w-96 space-y-3 p-4" data-courier-ride-panel>
        <p class="op-body">
          {{ courierRideLabel(props.choices.length) }} Uma corrida da TaOn leva
          as que você marcar, na ordem do percurso. O frete do cliente não muda.
        </p>
        <div class="space-y-2">
          <NuxtCheckbox
            v-for="choice in props.choices"
            :key="choice.card.ref"
            :model-value="picked.includes(choice.card.ref)"
            :label="choice.label"
            :description="rideOfferLine(choice)"
            :disabled="
              !picked.includes(choice.card.ref) &&
              picked.length >= MAX_RIDE_STOPS
            "
            data-courier-ride-order
            @update:model-value="(on) => toggle(choice.card.ref, Boolean(on))"
          />
        </div>
        <p
          v-if="props.choices.length > MAX_RIDE_STOPS"
          class="op-micro text-muted-foreground"
        >
          Uma corrida leva até {{ MAX_RIDE_STOPS }} pedidos.
        </p>

        <p
          v-if="quoteLine"
          class="op-body font-medium tabular-nums"
          role="status"
          data-courier-ride-quote
        >
          {{ quoteLine }}
        </p>

        <!-- troco que o entregador leva da gaveta, por pedido que pede -->
        <NuxtFormField
          v-for="choice in asksChange"
          :key="`change-${choice.card.ref}`"
          :label="`Troco do pedido ${code(choice.card.ref)}`"
          :description="choice.change_label || undefined"
          data-courier-ride-change
        >
          <NuxtInput
            v-model="changeOut[choice.card.ref]"
            class="w-full"
            type="text"
            inputmode="decimal"
            icon="i-lucide-circle-dollar-sign"
            :aria-label="`Troco que o entregador leva no pedido ${code(choice.card.ref)}`"
          />
        </NuxtFormField>

        <!-- a maquininha da corrida: uma só para todos os pedidos de cartão -->
        <div
          v-if="needsMachine && free.length >= 2"
          class="flex flex-col gap-1.5"
          data-courier-ride-machine
        >
          <p class="op-body font-medium">Qual maquininha vai na corrida?</p>
          <div class="grid grid-cols-2 gap-2">
            <NuxtButton
              v-for="opt in free"
              :key="opt.ref"
              type="button"
              :label="opt.label"
              :color="machineRef === opt.ref ? 'primary' : 'neutral'"
              :variant="machineRef === opt.ref ? 'solid' : 'outline'"
              @click="machineRef = opt.ref"
            />
          </div>
        </div>
        <p
          v-else-if="needsMachine && !free.length"
          class="op-body"
          data-courier-ride-no-machine
        >
          {{ machinesOutSentence(machines) }} Tire da corrida o pedido de cartão
          ou espere a maquininha voltar.
        </p>

        <NuxtAlert
          v-if="failure"
          color="error"
          variant="subtle"
          :description="failure"
          data-courier-ride-error
        />
        <NuxtButton
          block
          icon="i-lucide-bike"
          :label="
            courierRideCallLabel(
              picked.length,
              machine ? machine.label : undefined,
            )
          "
          :loading="sending"
          :disabled="!canCall"
          data-courier-ride-call
          @click="call"
        />
      </div>
    </template>
  </NuxtPopover>
</template>
