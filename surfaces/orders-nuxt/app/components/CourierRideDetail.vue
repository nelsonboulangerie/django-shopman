<script setup lang="ts">
// O detalhe da corrida: painel lateral (tela cheia no celular). O espelho diz o
// momento e o gesto; o detalhe responde "onde está, quando termina, como falo com
// ele, quanto custa" e guarda o gesto raro (cancelar, só antes da coleta).
//
// Só mostra o que a API da TaOn entrega (estudo de 14/11/2026): posição depois do
// aceite, entregador com telefone, hora de término da rota (não por parada), link
// de acompanhamento, cotação e valor final. Tirar ou trocar parada não existe na API.
import type {
  DeliveriesProjection,
  DeliveryRideProjection,
} from "~/generated/ordersContract";
import { rideColor } from "~/presentation/ridePalette";
import { rideLine, whatsappLink } from "~/presentation/deliveries";
import { clockHHMM } from "../../../operator-kit/app/presentation/courierProgress";

const props = defineProps<{
  ride: DeliveryRideProjection;
  origin: DeliveriesProjection["origin"];
  now: number;
  busy?: boolean;
  mapsKey?: string;
}>();
const emit = defineEmits<{ close: []; back: []; cancel: [] }>();
const tone = computed(() => rideColor(props.ride.number - 1));
const line = computed(() => rideLine(props.ride, props.now));
const located = computed(() =>
  props.ride.stops
    .filter((stop) => stop.latitude !== null && stop.longitude !== null)
    .map((stop) => ({ ...stop, latitude: stop.latitude as number, longitude: stop.longitude as number })),
);
const mapOrigin = computed(() => props.origin ?? located.value[0] ?? null);
const nextRef = computed(() => props.ride.stops.find((stop) => !stop.done)?.ref ?? "");
const copied = ref(false);
function copyLink() {
  void navigator.clipboard
    .writeText(props.ride.tracking_url)
    .then(() => {
      copied.value = true;
      setTimeout(() => (copied.value = false), 2000);
    })
    .catch(() => (copied.value = false));
}
const at = (iso: string) => (iso ? clockHHMM(Date.parse(iso)) : "");
</script>

<template>
  <aside class="flex h-full w-full flex-col overflow-hidden bg-default" data-ride-detail>
    <header class="flex items-start gap-3 border-b border-default px-5 py-4" :style="{ borderTop: `6px solid ${tone.bg}` }">
      <span class="grid size-9 shrink-0 place-items-center rounded-lg text-lg font-bold" :style="{ background: tone.bg, color: tone.fg }">{{ ride.number }}</span>
      <div class="min-w-0 flex-1">
        <p class="op-title font-semibold text-highlighted">Corrida {{ ride.number }} · {{ ride.status_label }}</p>
        <p class="op-body text-muted">{{ line.hint || line.title }}</p>
      </div>
      <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" aria-label="Fechar" @click="emit('close')" />
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div v-if="mapOrigin && located.length" class="relative mx-5 mt-4 h-48 overflow-hidden rounded-xl ring-1 ring-default">
        <CourierDeliveriesMap
          :origin="mapOrigin"
          :waiting="[]"
          :building="[]"
          :live="[{ number: ride.number, stops: located, courier: ride.position }]"
          :active="ride.number"
          :live-opacity="0.5"
          :maps-key="mapsKey"
          bare
        />
        <p v-if="ride.position" class="absolute right-2 bottom-2 rounded-md bg-white/90 px-2 py-1 op-micro text-toned shadow-sm">Posição pela TaOn</p>
      </div>

      <div v-if="ride.driver" class="mx-5 mt-4 flex items-center gap-3 rounded-xl bg-elevated/60 p-3">
        <NuxtAvatar :text="ride.driver.name.slice(0, 1)" size="lg" />
        <div class="min-w-0 flex-1">
          <p class="op-label font-semibold text-highlighted">{{ ride.driver.name }}</p>
          <p class="op-micro text-muted">{{ ride.driver.vehicle }}</p>
        </div>
        <template v-if="ride.driver.phone">
          <NuxtButton icon="i-lucide-phone" color="neutral" variant="outline" label="Ligar" :to="`tel:${ride.driver.phone.replace(/\D/g, '')}`" external />
          <NuxtButton icon="i-lucide-message-circle" color="neutral" variant="outline" square :aria-label="`WhatsApp de ${ride.driver.name}`" :to="whatsappLink(ride.driver.phone)" target="_blank" external />
        </template>
      </div>

      <section class="mx-5 mt-5">
        <p class="op-micro font-semibold text-muted">Paradas, na ordem do percurso</p>
        <ol class="mt-2 flex flex-col">
          <li v-for="(stop, i) in ride.stops" :key="stop.ref" class="relative flex gap-3 pb-4 last:pb-0">
            <span v-if="i < ride.stops.length - 1" class="absolute top-7 bottom-0 left-3.5 w-px bg-default" aria-hidden="true" />
            <span class="relative z-10 grid size-7 shrink-0 place-items-center rounded-full border-[3px] bg-white op-micro font-bold text-highlighted" :style="{ borderColor: tone.bg }">
              <NuxtIcon v-if="stop.done" name="i-lucide-check" class="size-3.5" /><template v-else>{{ i + 1 }}</template>
            </span>
            <div class="min-w-0 flex-1">
              <p class="flex items-baseline gap-2">
                <span class="op-body font-medium" :class="stop.done ? 'text-muted' : 'text-highlighted'">{{ stop.code }} · {{ stop.customer }}</span>
                <span class="ml-auto shrink-0 op-micro" :class="stop.done ? 'text-success' : stop.ref === nextRef && ride.state === 'route' ? 'font-semibold text-highlighted' : 'text-muted'">
                  {{ stop.done ? "entregue" : stop.ref === nextRef && ride.state === "route" ? "indo para cá" : stop.volumes ? `${stop.volumes} ${stop.volumes === 1 ? "sacola" : "sacolas"}` : "sacolas?" }}
                </span>
              </p>
              <p class="truncate op-micro text-muted">{{ stop.address }}</p>
              <NuxtButton class="-ml-2" color="neutral" variant="ghost" label="Abrir o pedido" trailing-icon="i-lucide-arrow-up-right" :to="`/${encodeURIComponent(stop.ref)}`" />
            </div>
          </li>
        </ol>
      </section>

      <section v-if="ride.tracking_url" class="mx-5 mt-5 flex items-center gap-3 rounded-xl border border-default p-3">
        <NuxtIcon name="i-lucide-map-pinned" class="size-5 text-muted" />
        <p class="min-w-0 flex-1 op-body text-toned">Link de acompanhamento da corrida.</p>
        <NuxtButton color="neutral" variant="outline" :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'" :label="copied ? 'Copiado' : 'Copiar link'" @click="copyLink" />
      </section>

      <section class="mx-5 mt-5">
        <p class="op-micro font-semibold text-muted">O que aconteceu</p>
        <ul class="mt-2 flex flex-col gap-1.5 op-body">
          <li v-if="ride.called_at" class="flex gap-3"><span class="w-11 shrink-0 tabular-nums text-muted">{{ at(ride.called_at) }}</span><span class="text-highlighted">Corrida chamada</span></li>
          <li v-if="ride.pickup_eta_at && ride.state === 'coming'" class="flex gap-3"><span class="w-11 shrink-0 tabular-nums text-muted">{{ at(ride.pickup_eta_at) }}</span><span class="text-highlighted">Chegada prevista na loja</span></li>
          <li v-if="ride.arrived_pickup_at" class="flex gap-3"><span class="w-11 shrink-0 tabular-nums text-muted">{{ at(ride.arrived_pickup_at) }}</span><span class="text-highlighted">Chegou na loja</span></li>
          <li v-if="ride.picked_up_at" class="flex gap-3"><span class="w-11 shrink-0 tabular-nums text-muted">{{ at(ride.picked_up_at) }}</span><span class="text-highlighted">Saiu com as sacolas</span></li>
          <li v-if="ride.delivery_eta_at" class="flex gap-3"><span class="w-11 shrink-0 tabular-nums text-muted">{{ at(ride.delivery_eta_at) }}</span><span class="text-highlighted">Término previsto da rota</span></li>
        </ul>
      </section>

      <section v-if="ride.cost_display || ride.back_lines.length" class="mx-5 mt-5 mb-5 flex flex-col gap-2">
        <div v-if="ride.cost_display" class="rounded-xl bg-elevated/60 p-3">
          <p class="op-micro text-muted">A corrida, paga pela casa</p>
          <p class="op-title font-semibold tabular-nums text-highlighted">{{ ride.cost_display }}</p>
        </div>
        <div v-if="ride.back_lines.length" class="rounded-xl bg-elevated/60 p-3">
          <p class="op-micro text-muted">Volta com</p>
          <p v-for="item in ride.back_lines" :key="item" class="op-body text-highlighted">{{ item }}</p>
        </div>
      </section>
    </div>

    <footer class="flex flex-wrap items-center gap-2 border-t border-default px-5 py-3">
      <template v-if="ride.back_action">
        <NuxtButton class="flex-1 justify-center" color="primary" icon="i-lucide-undo-2" :label="ride.back_action.label" :loading="busy" :disabled="!ride.back_action.enabled" @click="emit('back')" />
      </template>
      <template v-else-if="ride.cancel_action">
        <p class="min-w-0 flex-1 op-micro text-muted">Antes de ele sair com as sacolas, dá para cancelar.</p>
        <NuxtButton color="error" variant="ghost" icon="i-lucide-circle-x" :label="ride.cancel_action.label" :loading="busy" :disabled="!ride.cancel_action.enabled" @click="emit('cancel')" />
      </template>
      <p v-else class="min-w-0 flex-1 op-micro text-muted">Ele já saiu com as sacolas: cancelar agora só pela central da TaOn.</p>
    </footer>
  </aside>
</template>
