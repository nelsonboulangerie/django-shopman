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
import { rideLine, rideNotice, whatsappLink } from "~/presentation/deliveries";
import { courierCancelNotice } from "../../../operator-kit/app/presentation/courierCancel";
import { clockHHMM } from "../../../operator-kit/app/presentation/courierProgress";

const props = defineProps<{
  ride: DeliveryRideProjection;
  origin: DeliveriesProjection["origin"];
  now: number;
  busy?: boolean;
  mapsKey?: string;
}>();
const emit = defineEmits<{ close: []; back: []; cancel: [reasonId?: number] }>();
const tone = computed(() => rideColor(props.ride.number - 1));
const line = computed(() => rideLine(props.ride, props.now));
// O aviso de "não chame de novo" se dispensa, e volta se a causa mudar
// (outra desistência na mesma corrida).
const notice = computed(() => rideNotice(props.ride, props.now));
const noticeDismissedFor = ref("");
const showNotice = computed(() => notice.value !== null && noticeDismissedFor.value !== notice.value.key);
function dismissNotice() {
  noticeDismissedFor.value = notice.value?.key ?? "";
}
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

// Cancelar a corrida: o primeiro toque só arma a confirmação (um toque nunca
// cancela); o segundo confirma e, depois do aceite, já diz o motivo. Se a corrida
// muda enquanto a confirmação está aberta (aceite, coleta), ela desarma: a
// pergunta de antes já não é a de agora.
const confirmingCancel = ref(false);
watch(
  () => JSON.stringify(props.ride.cancel_action?.payload_schema ?? null),
  () => (confirmingCancel.value = false),
);
function confirmCancel(reasonId?: number) {
  confirmingCancel.value = false;
  emit("cancel", reasonId);
}

// O cancelamento pedido: espera, dúvida ou recusa da TaOn. Dispensável, e volta
// se o estado mudar (a recusa depois da espera é outro aviso).
const cancelState = computed(() => courierCancelNotice(props.ride.cancel_state, props.ride.cancel_message));
const cancelDismissed = ref("");
const showCancelState = computed(
  () => Boolean(cancelState.value) && cancelDismissed.value !== `${props.ride.key}:${props.ride.cancel_state}`,
);
</script>

<template>
  <aside class="flex h-full w-full flex-col overflow-hidden bg-default" data-ride-detail>
    <header class="flex items-start gap-3 border-b border-default px-5 py-4" :style="{ borderTop: `6px solid ${tone.bg}` }">
      <span class="grid size-9 shrink-0 place-items-center rounded-lg text-lg font-bold" :style="{ background: tone.bg, color: tone.fg }">{{ ride.letter }}</span>
      <div class="min-w-0 flex-1">
        <p class="op-title font-semibold text-highlighted">Corrida {{ ride.letter }} · {{ ride.status_label }}</p>
        <p class="op-body text-muted">{{ line.hint || line.title }}</p>
      </div>
      <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" aria-label="Fechar" @click="emit('close')" />
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <NuxtAlert
        v-if="notice && showNotice"
        class="mx-5 mt-4 w-auto"
        :color="notice.color"
        variant="subtle"
        :icon="notice.icon"
        :title="notice.title"
        :description="notice.description"
        close
        role="status"
        data-ride-notice
        @update:open="dismissNotice"
      />

      <!-- A margem mora no invólucro: o aviso é `w-full`, e com a margem nele o X vazava do painel. -->
      <div v-if="showCancelState && cancelState" class="mx-5 mt-4">
        <NuxtAlert
          :color="cancelState.color"
          variant="subtle"
          :icon="cancelState.icon"
          :title="cancelState.message"
          close
          role="status"
          data-ride-cancel-state
          @update:open="cancelDismissed = `${ride.key}:${ride.cancel_state}`"
        />
      </div>
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
          <li v-if="ride.state === 'reopened' && ride.reopened_at" class="flex gap-3"><span class="w-11 shrink-0 tabular-nums text-muted">{{ at(ride.reopened_at) }}</span><span class="font-semibold text-highlighted">{{ ride.reopened_driver || "O entregador" }} desistiu</span></li>
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

    <!-- Com o cancelamento pedido, o aviso do topo já diz tudo: o rodapé não repete nem oferece gesto. -->
    <footer v-if="ride.back_action || ride.cancel_action || ride.cancel_state !== 'pending'" class="flex flex-wrap items-center gap-2 border-t border-default px-5 py-3" data-ride-footer>
      <template v-if="ride.back_action">
        <NuxtButton class="flex-1 justify-center" color="primary" icon="i-lucide-undo-2" :label="ride.back_action.label" :loading="busy" :disabled="!ride.back_action.enabled" @click="emit('back')" />
      </template>
      <template v-else-if="ride.cancel_action">
        <CourierCancelConfirm v-if="confirmingCancel" :action="ride.cancel_action" :busy="busy" @confirm="confirmCancel" @keep="confirmingCancel = false" />
        <template v-else>
          <p class="min-w-0 flex-1 op-micro text-muted">{{ notice?.footer ?? "Antes de ele sair com as sacolas, dá para cancelar." }}</p>
          <NuxtButton color="error" variant="ghost" icon="i-lucide-circle-x" :label="ride.cancel_action.label" :loading="busy" :disabled="!ride.cancel_action.enabled" :title="ride.cancel_action.reason || undefined" data-ride-cancel @click="confirmingCancel = true" />
        </template>
      </template>
      <p v-else-if="ride.cancel_state === 'unknown'" class="min-w-0 flex-1 op-micro text-muted">Confira esta corrida na central da TaOn antes de pedir o cancelamento de novo.</p>
      <p v-else class="min-w-0 flex-1 op-micro text-muted">{{ notice?.footer ?? "Ele já saiu com as sacolas: cancelar agora só pela central da TaOn." }}</p>
    </footer>
  </aside>
</template>
