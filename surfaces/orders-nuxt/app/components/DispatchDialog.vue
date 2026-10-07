<script setup lang="ts">
// Saída para entrega. Só abre quando há o que perguntar: troco a levar, outro
// pedido pronto que pode ir junto, ou maquininha a escolher (as duas livres) /
// sem nenhuma livre. Com uma livre e nada mais, a saída é um toque no card.
import type { OrderCardProjection } from "~/types/orders";
import {
  dispatchAsksChange,
  dispatchSteps,
  freeMachines,
  machinePhrase,
  machinesOutSentence,
  moneyInput,
  splitRef,
  tripCandidates,
  type DispatchStep,
} from "~/presentation/board";

const props = defineProps<{
  card: OrderCardProjection | null;
  cards: OrderCardProjection[];
  busy?: boolean;
}>();
const emit = defineEmits<{
  (e: "dispatch", steps: DispatchStep[]): void;
  (e: "courier-back", orderRef: string): void;
  (e: "close"): void;
}>();

const together = ref<string[]>([]);
const changeOut = ref<Record<string, string>>({});
watch(
  () => props.card?.ref,
  () => {
    together.value = [];
    changeOut.value =
      props.card && dispatchAsksChange(props.card)
        ? { [props.card.ref]: moneyInput(props.card.change_out_suggested_q) }
        : {};
  },
  { immediate: true },
);

const candidates = computed(() =>
  props.card ? tripCandidates(props.card, props.cards) : [],
);
const candidateOptions = computed(() =>
  candidates.value.map((candidate) => ({
    value: candidate.ref,
    label: `Pedido ${code(candidate.ref)}${candidate.customer_name ? ` · ${candidate.customer_name}` : ""}`,
  })),
);
const trip = computed(() =>
  props.card
    ? [
        props.card,
        ...candidates.value.filter((c) => together.value.includes(c.ref)),
      ]
    : [],
);
const machineCard = computed(
  () => trip.value.find((c) => c.dispatch_needs_machine) ?? null,
);
const free = computed(() =>
  machineCard.value ? freeMachines(machineCard.value.equipment_options) : [],
);
const asksChange = computed(() =>
  trip.value.filter((c) => dispatchAsksChange(c)),
);
const onRoad = computed(() =>
  (machineCard.value?.equipment_options ?? []).filter(
    (opt) => opt.ref.startsWith("card_machine:") && opt.order_ref,
  ),
);
const primaryLabel = computed(() => {
  if (!machineCard.value) return "Saiu para entrega";
  return free.value.length === 1
    ? `Saiu com a ${machinePhrase(free.value[0]!.label)}`
    : "";
});

function updateTogether(next: string[]) {
  for (const ref_ of next.filter(
    (candidate) => !together.value.includes(candidate),
  )) {
    const card = candidates.value.find((candidate) => candidate.ref === ref_);
    if (
      card &&
      dispatchAsksChange(card) &&
      changeOut.value[ref_] === undefined
    ) {
      changeOut.value = {
        ...changeOut.value,
        [ref_]: moneyInput(card.change_out_suggested_q),
      };
    }
  }
  together.value = next;
}
function go(machineRef?: string) {
  const ref_ =
    machineRef ?? (machineCard.value ? free.value[0]?.ref : undefined);
  emit(
    "dispatch",
    dispatchSteps(trip.value, { machineRef: ref_, changeOut: changeOut.value }),
  );
}
const code = (ref_: string) => splitRef(ref_).code;
</script>

<template>
  <NuxtModal
    :open="card != null"
    title="Saída para entrega"
    :description="`Pedido ${card ? code(card.ref) : ''}${card?.customer_name ? ` · ${card.customer_name}` : ''}`"
    data-dispatch-dialog
    @update:open="
      (v) => {
        if (!v) emit('close');
      }
    "
  >
    <template #body>
      <div class="grid gap-4">
        <!-- outro pedido pronto: vai junto na mesma saída (uma maquininha só) -->
        <NuxtFormField v-if="candidates.length" label="Vai junto nesta saída?">
          <NuxtCheckboxGroup
            :model-value="together"
            :items="candidateOptions"
            variant="table"
            data-dispatch-together
            @update:model-value="updateTogether"
          />
        </NuxtFormField>

        <!-- troco que o entregador leva da gaveta, por pedido que pede -->
        <NuxtFormField
          v-for="c in asksChange"
          :key="`change-${c.ref}`"
          :label="`Troco do pedido ${code(c.ref)}${c.change_label ? ` (${c.change_label})` : ''}`"
          data-dispatch-change
        >
          <NuxtInput
            v-model="changeOut[c.ref]"
            type="text"
            inputmode="decimal"
            icon="i-lucide-circle-dollar-sign"
            :aria-label="`Troco que o entregador leva no pedido ${code(c.ref)}`"
          />
        </NuxtFormField>

        <!-- maquininha: as duas livres → um toque na cor; nenhuma → onde elas estão -->
        <div
          v-if="machineCard && free.length >= 2"
          class="flex flex-col gap-1.5"
          data-dispatch-machine-choice
        >
          <p class="text-sm font-medium">Qual maquininha?</p>
          <div class="grid grid-cols-2 gap-2">
            <NuxtButton
              v-for="opt in free"
              :key="opt.ref"
              type="button"
              :label="opt.label"
              color="primary"
              :disabled="busy"
              @click="go(opt.ref)"
            />
          </div>
        </div>
        <div
          v-else-if="machineCard && !free.length"
          class="flex flex-col gap-2"
          data-dispatch-no-machine
        >
          <p class="text-sm font-medium">
            {{ machinesOutSentence(machineCard.equipment_options) }}
          </p>
          <NuxtButton
            v-for="opt in onRoad"
            :key="opt.ref"
            type="button"
            :label="`Entregador do ${code(opt.order_ref)} voltou`"
            color="neutral"
            variant="outline"
            :disabled="busy"
            @click="emit('courier-back', opt.order_ref)"
          />
        </div>
      </div>
    </template>
    <template #footer>
      <NuxtButton
        label="Voltar"
        color="neutral"
        variant="outline"
        @click="emit('close')"
      />
      <NuxtButton
        v-if="primaryLabel"
        :label="primaryLabel"
        color="primary"
        :disabled="busy"
        :loading="busy"
        @click="go()"
      />
    </template>
  </NuxtModal>
</template>
