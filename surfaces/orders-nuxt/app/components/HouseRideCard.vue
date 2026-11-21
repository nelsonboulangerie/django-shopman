<script setup lang="ts">
// A corrida da casa, forma E (M3b, #2898; prévia 2 do plano das Entregas): o trilho e a
// letra na cor da corrida, os códigos com "∙" à esquerda e "N pedidos" ao lado da letra.
// O momento diz quem leva ("Diego leva", "Diego na rua · 1 de 2 entregues"), e os gestos
// (`HouseRideGestures`) são os do balcão para quando o entregador está sem celular. Mora na
// lista de Corridas das Entregas e na coluna Saída dos Pedidos (M3d, #2937). A página é
// dona dos gestos.
import type { DeliveryRideProjection } from "~/generated/ordersContract";
import { rideColor } from "~/presentation/ridePalette";
import { houseCodes, ordersWord, type HouseGesture } from "~/presentation/houseCouriers";

const props = defineProps<{ ride: DeliveryRideProjection; busy?: string }>();
const emit = defineEmits<{ gesture: [gesture: HouseGesture]; back: [] }>();

const tone = computed(() => rideColor(props.ride.number - 1));
const house = computed(() => props.ride.house!);
const codes = computed(() => houseCodes(props.ride.stops));
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

      <HouseRideGestures :ride="ride" :busy="busy" @gesture="(item) => emit('gesture', item)" @back="emit('back')" />
    </div>
  </div>
</template>
