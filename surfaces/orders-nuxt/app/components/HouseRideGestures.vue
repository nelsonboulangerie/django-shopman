<script setup lang="ts">
// Os gestos do balcão na corrida da casa (M3b, #2898; M3d, #2937), um lugar só para o
// cartão da lista de Corridas, o detalhe da corrida e a coluna Saída dos Pedidos:
// "Despachar a corrida C", "A47 entregue", "Reenviar o link", "Soltar o link" e "Ligar para
// Diego". O desenho (dono, 21/11: "bem feios e desorganizados no mobile"): o gesto do
// momento em largura total; os outros em duas colunas iguais, o último sozinho ocupa as duas.
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
// Com o "Entregador voltou" à vista, ele é o gesto do momento e os outros descem.
const primaries = computed(() => (back.value ? [] : gestures.value.filter((item) => item.primary)));
const secondaries = computed(() => (back.value ? gestures.value : gestures.value.filter((item) => !item.primary)));
const secondaryCount = computed(() => secondaries.value.length + (call.value ? 1 : 0));
// O último secundário que sobra sozinho na linha ocupa as duas colunas.
const spans = (index: number) => secondaryCount.value % 2 === 1 && index === secondaryCount.value - 1;
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

  <!-- os gestos do balcão: o do momento em largura total, os outros em duas colunas iguais -->
  <div v-else-if="gestures.length || back || call" class="grid grid-cols-2 gap-2 pt-1.5" data-house-ride-gestures>
    <NuxtButton
      v-if="back"
      block
      color="primary"
      class="col-span-2 min-h-11"
      icon="i-lucide-undo-2"
      :label="back.label"
      :disabled="!back.enabled"
      :loading="busy === 'back'"
      @click="emit('back')"
    />
    <NuxtButton
      v-for="item in primaries"
      :key="item.key"
      block
      color="primary"
      class="col-span-2 min-h-11"
      :icon="item.icon"
      :label="item.action.label"
      :disabled="!item.action.enabled"
      :title="item.action.reason || undefined"
      :loading="busy === item.key"
      :data-house-gesture="item.key"
      @click="tap(item)"
    />
    <NuxtButton
      v-for="(item, index) in secondaries"
      :key="item.key"
      block
      color="neutral"
      variant="outline"
      class="min-h-11"
      :class="spans(index) ? 'col-span-2' : ''"
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
      block
      color="neutral"
      variant="outline"
      class="min-h-11"
      :class="spans(secondaries.length) ? 'col-span-2' : ''"
      icon="i-lucide-phone"
      :label="call.label"
      :to="call.href"
      external
      data-house-call
    />
  </div>
</template>
