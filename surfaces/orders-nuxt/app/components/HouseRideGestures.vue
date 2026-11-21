<script setup lang="ts">
// Os gestos do balcão na corrida da casa (M3b, #2898; M3d, #2937), um lugar só para o
// cartão da lista de Corridas, o detalhe da corrida e a coluna Saída dos Pedidos:
// "Saiu", "A47 entregue", "Reenviar o link", "Soltar o link" e "Ligar para Diego".
// Gesto que avisa cliente ou mexe no link pede confirmação: o primeiro toque arma, a
// frase diz o que vai acontecer, o segundo faz. A página é dona dos gestos.
import type { Action, DeliveryRideProjection } from "~/generated/ordersContract";
import { callCourier, houseGestures, type HouseGesture } from "~/presentation/houseCouriers";

const props = withDefaults(
  defineProps<{
    ride: DeliveryRideProjection;
    busy?: string;
    /** O "Entregador voltou" mora aqui (o cartão) ou no rodapé de quem chama (o detalhe). */
    withBack?: boolean;
    /** O "Ligar para Diego" mora aqui (o cartão) ou no cartão do entregador (o detalhe). */
    withCall?: boolean;
  }>(),
  { busy: "", withBack: true, withCall: true },
);
const emit = defineEmits<{ gesture: [gesture: HouseGesture]; back: [] }>();

const gestures = computed(() => houseGestures(props.ride));
const call = computed(() => (props.withCall ? callCourier(props.ride) : null));
const armed = ref("");
const armedGesture = computed(() => gestures.value.find((item) => item.key === armed.value) ?? null);
function tap(item: HouseGesture) {
  const confirmation = item.action.confirmation as { required?: boolean } | undefined;
  if (confirmation?.required && armed.value !== item.key) {
    armed.value = item.key;
    return;
  }
  armed.value = "";
  emit("gesture", item);
}
const description = (action: Action) => String((action.confirmation as { description?: string })?.description ?? "");
const back = computed(() => (props.withBack ? props.ride.back_action : null));
</script>

<template>
  <!-- a confirmação do gesto armado: o que vai acontecer, e o segundo toque -->
  <div v-if="armedGesture" class="mt-1 flex flex-col gap-2 rounded-lg bg-elevated/60 p-2" data-house-ride-confirm>
    <p class="op-body text-highlighted">{{ description(armedGesture.action) }}</p>
    <div class="flex flex-wrap gap-2">
      <NuxtButton color="primary" class="min-h-11" :icon="armedGesture.icon" :label="armedGesture.action.label" :loading="busy === armedGesture.key" @click="tap(armedGesture)" />
      <NuxtButton color="neutral" variant="ghost" class="min-h-11" label="Agora não" @click="armed = ''" />
    </div>
  </div>

  <!-- os gestos do balcão -->
  <div v-else-if="gestures.length || back || call" class="flex flex-wrap gap-2 pt-1.5" data-house-ride-gestures>
    <NuxtButton
      v-if="back"
      color="primary"
      class="min-h-11"
      icon="i-lucide-undo-2"
      :label="back.label"
      :disabled="!back.enabled"
      :loading="busy === 'back'"
      @click="emit('back')"
    />
    <NuxtButton
      v-for="item in gestures"
      :key="item.key"
      class="min-h-11"
      :color="item.primary && !back ? 'primary' : 'neutral'"
      :variant="item.primary && !back ? 'solid' : 'outline'"
      :icon="item.icon"
      :label="item.action.label"
      :disabled="!item.action.enabled"
      :title="item.action.reason || undefined"
      :loading="busy === item.key"
      :data-house-gesture="item.key"
      @click="tap(item)"
    />
    <NuxtButton
      v-if="call"
      class="min-h-11"
      color="neutral"
      variant="outline"
      icon="i-lucide-phone"
      :label="call.label"
      :to="call.href"
      external
      data-house-call
    />
  </div>
</template>
