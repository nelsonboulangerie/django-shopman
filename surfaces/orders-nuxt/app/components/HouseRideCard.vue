<script setup lang="ts">
// A corrida da casa, forma E (M3b, #2898; prévia 2 do plano das Entregas): o trilho e a
// letra na cor da corrida, os códigos com "∙" à esquerda e "N pedidos" ao lado da letra.
// O momento diz quem leva ("Diego leva", "Diego na rua · 1 de 2 entregues"), e os gestos
// são os do balcão para quando o entregador está sem celular: "Saiu", "A47 entregue",
// "Reenviar o link" e "Soltar o link". O acerto continua o "Entregador voltou" de sempre.
// Gesto que avisa cliente ou mexe no link pede confirmação: o primeiro toque arma, a
// frase diz o que vai acontecer, o segundo faz. A página é dona dos gestos.
import type { Action, DeliveryRideProjection } from "~/generated/ordersContract";
import { rideColor } from "~/presentation/ridePalette";
import { houseCodes, houseGestures, ordersWord, type HouseGesture } from "~/presentation/houseCouriers";

const props = defineProps<{ ride: DeliveryRideProjection; busy?: string }>();
const emit = defineEmits<{ gesture: [gesture: HouseGesture]; back: [] }>();

const tone = computed(() => rideColor(props.ride.number - 1));
const house = computed(() => props.ride.house!);
const codes = computed(() => houseCodes(props.ride.stops));
const gestures = computed(() => houseGestures(props.ride));
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
const onRoad = computed(() => props.ride.stops.some((stop) => stop.done) || house.value.deliver_actions.length > 0);
</script>

<template>
  <div
    class="flex flex-col overflow-hidden rounded-xl border border-default bg-default shadow-xs"
    data-house-ride
    :data-ride-letter="ride.letter"
  >
    <span class="h-1.5 shrink-0" :style="{ background: tone.bg }" aria-hidden="true" />
    <div class="flex min-w-0 flex-col gap-1 p-3">
      <!-- identidade: os códigos à esquerda; a quantidade e a letra no canto -->
      <NuxtLink
        :to="{ path: '/delivery', query: { ride: ride.key } }"
        class="flex min-h-11 min-w-0 items-center gap-2 rounded-lg focus-visible:outline-2 focus-visible:outline-primary"
        :aria-label="`Corrida ${ride.letter}: ${codes.map((item) => item.code).join(', ')}`"
      >
        <span class="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-1 text-xl leading-tight font-bold tabular-nums text-highlighted" data-house-ride-codes>
          <template v-for="(item, index) in codes" :key="item.code">
            <span v-if="index" class="font-normal text-muted" aria-hidden="true">∙</span>
            <span :class="item.done ? 'text-muted line-through decoration-2' : ''">{{ item.code }}</span>
          </template>
        </span>
        <span class="shrink-0 op-micro whitespace-nowrap text-muted">{{ ordersWord(ride.stops.length) }}</span>
        <span
          class="grid size-7 shrink-0 place-items-center rounded-md op-label font-bold"
          :style="{ background: tone.bg, color: tone.fg }"
          data-house-ride-letter
        >{{ ride.letter }}</span>
      </NuxtLink>

      <!-- momento: quem leva -->
      <p class="mt-1 flex items-center gap-1.5 op-body font-semibold text-highlighted" data-house-ride-moment>
        <NuxtIcon :name="onRoad ? 'i-lucide-navigation' : 'i-lucide-user-round'" class="size-4 shrink-0 text-muted" />
        <span class="min-w-0">{{ house.moment }}</span>
      </p>
      <p v-if="house.hint" class="op-micro text-toned" data-house-ride-hint>{{ house.hint }}</p>

      <!-- destino: uma linha por parada -->
      <ul class="flex flex-col gap-0.5">
        <li v-for="stop in ride.stops" :key="stop.ref" class="flex min-w-0 items-baseline gap-1.5 op-micro">
          <span v-if="ride.stops.length > 1" class="w-9 shrink-0 font-semibold tabular-nums" :class="stop.done ? 'text-muted line-through' : 'text-toned'">{{ stop.code }}</span>
          <span class="min-w-0 text-toned">{{ stop.place }}<template v-if="stop.volumes"> · {{ stop.volumes }} {{ stop.volumes === 1 ? "sacola" : "sacolas" }}</template><template v-if="stop.change_label"> · {{ stop.change_label }}</template></span>
        </li>
      </ul>

      <!-- a confirmação do gesto armado: o que vai acontecer, e o segundo toque -->
      <div v-if="armedGesture" class="mt-1 flex flex-col gap-2 rounded-lg bg-elevated/60 p-2" data-house-ride-confirm>
        <p class="op-body text-highlighted">{{ description(armedGesture.action) }}</p>
        <div class="flex flex-wrap gap-2">
          <NuxtButton color="primary" class="min-h-11" :icon="armedGesture.icon" :label="armedGesture.action.label" :loading="busy === armedGesture.key" @click="tap(armedGesture)" />
          <NuxtButton color="neutral" variant="ghost" class="min-h-11" label="Agora não" @click="armed = ''" />
        </div>
      </div>

      <!-- os gestos do balcão -->
      <div v-else-if="gestures.length || ride.back_action" class="flex flex-wrap gap-2 pt-1.5" data-house-ride-gestures>
        <NuxtButton
          v-if="ride.back_action"
          color="primary"
          class="min-h-11"
          icon="i-lucide-undo-2"
          :label="ride.back_action.label"
          :disabled="!ride.back_action.enabled"
          :loading="busy === 'back'"
          @click="emit('back')"
        />
        <NuxtButton
          v-for="item in gestures"
          :key="item.key"
          class="min-h-11"
          :color="item.primary && !ride.back_action ? 'primary' : 'neutral'"
          :variant="item.primary && !ride.back_action ? 'solid' : 'outline'"
          :icon="item.icon"
          :label="item.action.label"
          :disabled="!item.action.enabled"
          :title="item.action.reason || undefined"
          :loading="busy === item.key"
          :data-house-gesture="item.key"
          @click="tap(item)"
        />
      </div>
    </div>
  </div>
</template>
