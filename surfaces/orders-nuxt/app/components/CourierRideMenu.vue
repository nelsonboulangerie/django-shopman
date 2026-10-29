<script setup lang="ts">
// Uma corrida da TaOn para várias entregas prontas: o botão do cabeçalho aparece
// com duas ou mais que podem ir juntas (`ride_candidates`: sem corrida, sem
// maquininha e sem troco da gaveta) e abre a escolha. A TaOn leva os pedidos numa
// solicitação só, na ordem do percurso; o custo é da casa e o frete do cliente
// não muda. A recusa do servidor (pedido que mudou) aparece aqui mesmo.
import type { OrderCardProjection } from "~/types/orders";
import {
  courierRideLabel,
  courierRideLine,
  MAX_RIDE_STOPS,
} from "~/presentation/board";

const props = defineProps<{ candidates: OrderCardProjection[] }>();
const emit = defineEmits<{ done: [] }>();

const open = ref(false);
const picked = ref<string[]>([]);
const sending = ref(false);
const failure = ref("");

watch(open, (isOpen) => {
  if (!isOpen) return;
  failure.value = "";
  picked.value = props.candidates
    .slice(0, MAX_RIDE_STOPS)
    .map((card) => card.ref);
});

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
      body: { refs: picked.value },
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
</script>

<template>
  <NuxtPopover
    v-if="props.candidates.length >= 2"
    v-model:open="open"
    :content="{ align: 'end' }"
  >
    <NuxtButton
      icon="i-lucide-route"
      :label="courierRideLabel(props.candidates.length)"
      color="neutral"
      variant="outline"
      data-courier-ride-menu
    />
    <template #content>
      <div class="w-80 space-y-3 p-4" data-courier-ride-panel>
        <p class="op-body">
          Uma corrida da TaOn leva estas entregas, na ordem do percurso. O frete
          do cliente não muda.
        </p>
        <div class="space-y-2">
          <NuxtCheckbox
            v-for="card in props.candidates"
            :key="card.ref"
            :model-value="picked.includes(card.ref)"
            :label="courierRideLine(card)"
            :description="card.delivery_address"
            :disabled="
              !picked.includes(card.ref) && picked.length >= MAX_RIDE_STOPS
            "
            data-courier-ride-order
            @update:model-value="(on) => toggle(card.ref, Boolean(on))"
          />
        </div>
        <p
          v-if="props.candidates.length > MAX_RIDE_STOPS"
          class="op-micro text-muted-foreground"
        >
          Uma corrida leva até {{ MAX_RIDE_STOPS }} pedidos.
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
          :label="`Chamar uma corrida para ${picked.length} pedidos`"
          :loading="sending"
          :disabled="picked.length < 2"
          data-courier-ride-call
          @click="call"
        />
      </div>
    </template>
  </NuxtPopover>
</template>
