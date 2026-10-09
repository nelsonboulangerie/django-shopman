<script setup lang="ts">
// Courier ride panel — the operator's window into the external delivery
// (Machine): compact step timeline, driver card, tracking link, quoted cost,
// and the ride actions (quote / dispatch / cancel). Status text comes from the
// server projection; steps/tones are derived from the raw letter.
import {
  courierFailed,
  courierSteps,
  courierTone,
} from "~/presentation/courier";
import type { Action } from "~/generated/ordersContract";
import type { CourierBlock } from "~/types/orders";

const props = defineProps<{
  courier: CourierBlock;
  busy: boolean;
  cancelAction?: Action;
  quoteAction?: Action;
  dispatchAction?: Action;
}>();
const emit = defineEmits<{ quote: []; dispatch: []; cancel: [] }>();

const steps = computed(() => courierSteps(props.courier.status));
const tone = computed(() => courierTone(props.courier.status));
const failed = computed(() => courierFailed(props.courier.status));
const hasRide = computed(() => Boolean(props.courier.status));
const timelineItems = computed(() =>
  steps.value.map((step) => ({
    value: step.key,
    title: step.label,
    icon: step.state === "done" ? "i-lucide-check" : undefined,
  })),
);
const currentStep = computed(
  () =>
    steps.value.find((step) => step.state === "current")?.key ??
    steps.value.at(-1)?.key,
);

// Cancelar corrida é irreversível para a solicitação em curso → confirm de 1 toque.
const confirmingCancel = ref(false);
watch(
  () => JSON.stringify(props.cancelAction?.payload_schema),
  () => {
    confirmingCancel.value = false;
  },
);
function requestCancel() {
  if (!confirmingCancel.value) {
    confirmingCancel.value = true;
    return;
  }
  confirmingCancel.value = false;
  emit("cancel");
}

const telHref = (phone: string) => `tel:${phone.replace(/[^\d+]/g, "")}`;
</script>

<template>
  <NuxtCard as="section">
    <template #header>
      <div class="flex flex-wrap items-center gap-2">
        <h2 class="flex items-center gap-1.5 op-title">
          <Icon name="lucide:bike" class="size-4" /> Entregador
        </h2>
        <NuxtBadge
          v-if="courier.status_label"
          :color="
            tone === 'danger'
              ? 'error'
              : tone === 'success'
                ? 'success'
                : tone === 'info'
                  ? 'info'
                  : tone === 'active'
                    ? 'primary'
                    : 'neutral'
          "
          :label="courier.status_label"
        />
        <span
          v-if="courier.attempts_count > 0"
          class="text-xs text-muted-foreground"
        >
          {{ courier.attempts_count }}ª corrida não concluída
        </span>
        <span
          v-if="courier.estimate_display"
          class="ms-auto text-sm tabular-nums text-muted-foreground"
        >
          {{ courier.final_value_display || courier.estimate_display }}
        </span>
      </div>
    </template>

    <div class="flex flex-col gap-3">
      <!-- falha terminal do despacho (Machine recusou / dados) -->
      <NuxtAlert
        v-if="courier.error"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Falha ao abrir a corrida"
        :description="courier.error.message"
      />

      <!-- timeline compacta da corrida -->
      <NuxtTimeline
        v-if="steps.length"
        :items="timelineItems"
        :default-value="currentStep"
        orientation="horizontal"
        aria-label="Etapas da corrida"
      />
      <p v-else-if="failed" class="text-sm text-muted-foreground">
        A corrida não foi concluída. Re-despache ou combine a entrega por fora.
      </p>

      <!-- entregador -->
      <NuxtAlert
        v-if="courier.driver?.name"
        color="info"
        variant="subtle"
        icon="i-lucide-user"
        :title="courier.driver.name"
      >
        <template #description
          ><div class="flex flex-wrap items-center gap-x-4 gap-y-1">
            <NuxtButton
              v-if="courier.driver.phone"
              :to="telHref(courier.driver.phone)"
              icon="i-lucide-phone"
              :label="courier.driver.phone"
              variant="ghost"
            />
            <p
              v-if="
                courier.driver.vehicle_model || courier.driver.vehicle_plate
              "
              class="flex items-center gap-1.5 text-muted-foreground"
            >
              <Icon name="lucide:bike" class="size-4" />
              {{
                [courier.driver.vehicle_model, courier.driver.vehicle_plate]
                  .filter(Boolean)
                  .join(" · ")
              }}
            </p>
          </div></template
        >
      </NuxtAlert>

      <!-- rastreio + código de confirmação -->
      <div
        v-if="courier.tracking_url || courier.confirmation_code"
        class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm"
      >
        <NuxtButton
          v-if="courier.tracking_url"
          :to="courier.tracking_url"
          target="_blank"
          icon="i-lucide-map-pin"
          trailing-icon="i-lucide-external-link"
          label="Acompanhar corrida"
          variant="ghost"
        />
        <span
          v-if="courier.confirmation_code"
          class="flex items-center gap-1.5 text-muted-foreground"
        >
          <Icon name="lucide:key-round" class="size-4" /> Código:
          <strong class="tabular-nums">{{ courier.confirmation_code }}</strong>
        </span>
      </div>
    </div>

    <template
      v-if="courier.can_quote || courier.can_dispatch || courier.can_cancel"
      #footer
    >
      <div class="flex flex-wrap gap-2">
        <NuxtButton
          v-if="courier.can_dispatch"
          type="button"
          :disabled="busy || !dispatchAction?.enabled"
          :title="
            dispatchAction?.reason ||
            (dispatchAction?.enabled
              ? ''
              : 'Atualize o pedido para conferir esta ação.')
          "
          :icon="
            hasRide || courier.attempts_count > 0
              ? 'i-lucide-refresh-cw'
              : 'i-lucide-send'
          "
          :label="
            hasRide || courier.attempts_count > 0
              ? 'Chamar outro entregador'
              : 'Chamar entregador'
          "
          @click="emit('dispatch')"
        />
        <NuxtButton
          v-if="courier.can_quote"
          type="button"
          :disabled="busy || !quoteAction?.enabled"
          :title="
            quoteAction?.reason ||
            (quoteAction?.enabled
              ? ''
              : 'Atualize o pedido para conferir esta ação.')
          "
          icon="i-lucide-calculator"
          label="Cotar entrega"
          color="neutral"
          variant="outline"
          @click="emit('quote')"
        />
        <NuxtButton
          v-if="courier.can_cancel"
          type="button"
          :disabled="busy || !cancelAction?.enabled"
          icon="i-lucide-ban"
          :label="
            confirmingCancel
              ? 'Confirmar solicitação?'
              : 'Solicitar cancelamento'
          "
          color="error"
          variant="outline"
          @blur="confirmingCancel = false"
          @click="requestCancel"
        />
      </div>
    </template>
  </NuxtCard>
</template>
