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
import {
  freeMachines,
  machinePhrase,
  machinesOutSentence,
  moneyInput,
} from "~/presentation/board";
import type {
  Action,
  EquipmentOptionProjection,
} from "~/generated/ordersContract";
import type { CourierBlock } from "~/types/orders";

const props = defineProps<{
  courier: CourierBlock;
  busy: boolean;
  cancelAction?: Action;
  quoteAction?: Action;
  dispatchAction?: Action;
  /** As maquininhas do pedido (`order.equipment_options`), para a custódia. */
  equipmentOptions?: EquipmentOptionProjection[];
  dispatchAgainAction?: Action;
}>();
const emit = defineEmits<{
  quote: [];
  dispatch: [custody: { change_out?: string; equipment?: string[] }];
  cancel: [];
  dispatchAgain: [];
}>();

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

// Chamar entregador abre corrida paga na central → confirm de 1 toque, com a
// pergunta inteira (quem vem, para qual pedido, quem paga) vinda do servidor.
const confirmingDispatch = ref(false);
const dispatchQuestion = computed(() =>
  String(props.dispatchAction?.confirmation?.description ?? ""),
);
watch(
  () => JSON.stringify(props.dispatchAction?.payload_schema),
  () => {
    confirmingDispatch.value = false;
  },
);
// A custódia que sai com o entregador da TaOn, pré-preenchida pelo pedido:
// troco da gaveta e/ou a maquininha da casa. Pedido pago não pergunta nada.
const custody = computed(() => props.courier.custody);
const asksChange = computed(
  () => (custody.value?.change_out_suggested_q ?? 0) > 0,
);
const asksMachine = computed(() => Boolean(custody.value?.needs_machine));
const asksCustody = computed(() => asksChange.value || asksMachine.value);
const free = computed(() => freeMachines(props.equipmentOptions ?? []));
const changeOut = ref("");
const machineRef = ref("");
function armCustody() {
  changeOut.value = asksChange.value
    ? moneyInput(custody.value?.change_out_suggested_q ?? 0)
    : "";
  machineRef.value = free.value[0]?.ref ?? "";
}
const machineItems = computed(() =>
  free.value.map((opt) => ({ value: opt.ref, label: opt.label })),
);
const machineMissing = computed(() => asksMachine.value && !free.value.length);
function requestDispatch() {
  if (!confirmingDispatch.value) {
    armCustody();
    confirmingDispatch.value = true;
    return;
  }
  if (machineMissing.value) return;
  confirmingDispatch.value = false;
  emit("dispatch", {
    ...(asksChange.value ? { change_out: changeOut.value.trim() || "0" } : {}),
    ...(asksMachine.value ? { equipment: [machineRef.value] } : {}),
  });
}
function blurDispatch() {
  // Com campos a preencher, sair do botão não desarma: o operador está
  // conferindo o troco ou a maquininha. "Voltar" desarma.
  if (!asksCustody.value) confirmingDispatch.value = false;
}

const telHref = (phone: string) => `tel:${phone.replace(/[^\d+]/g, "")}`;
</script>

<template>
  <NuxtCard as="section">
    <div class="flex flex-col gap-3">
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

      <div class="flex flex-col gap-3">
        <!-- a TaOn não respondeu à última chamada: só ela trava chamar outra -->
        <NuxtAlert
          v-if="courier.can_dispatch_again"
          color="error"
          variant="subtle"
          icon="i-lucide-circle-help"
          :title="
            courier.error?.message ||
            'A TaOn não respondeu à última chamada.'
          "
          data-courier-no-answer
        >
          <template #actions>
            <NuxtButton
              type="button"
              color="error"
              variant="outline"
              icon="i-lucide-refresh-cw"
              label="Chamar de novo"
              :disabled="busy || !dispatchAgainAction?.enabled"
              :title="dispatchAgainAction?.reason || ''"
              @click="emit('dispatchAgain')"
            />
          </template>
        </NuxtAlert>

        <!-- falha terminal do despacho (Machine recusou / dados) -->
        <NuxtAlert
          v-else-if="courier.error"
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
          A corrida não foi concluída. Chame o entregador de novo.
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

      <template v-if="courier.can_quote || courier.can_dispatch || courier.can_cancel">
        <div
          v-if="confirmingDispatch"
          class="flex flex-col gap-3"
          data-testid="courier-dispatch-confirm"
        >
          <p
            v-if="dispatchQuestion"
            class="text-sm"
            role="status"
            data-testid="courier-dispatch-question"
          >
            {{ dispatchQuestion }}
          </p>
          <NuxtFormField
            v-if="asksChange"
            label="Troco que o entregador leva da gaveta"
            data-testid="courier-custody-change"
          >
            <NuxtInput
              v-model="changeOut"
              class="w-40"
              type="text"
              inputmode="decimal"
              icon="i-lucide-circle-dollar-sign"
              aria-label="Troco que o entregador leva da gaveta, em reais"
            />
          </NuxtFormField>
          <template v-if="asksMachine">
            <NuxtFormField
              v-if="free.length >= 2"
              label="Qual maquininha vai junto?"
              data-testid="courier-custody-machine"
            >
              <NuxtRadioGroup
                v-model="machineRef"
                :items="machineItems"
                orientation="horizontal"
              />
            </NuxtFormField>
            <p
              v-else-if="free.length === 1"
              class="text-sm"
              data-testid="courier-custody-machine"
            >
              Leva a {{ machinePhrase(free[0]!.label) }}.
            </p>
            <p
              v-else
              class="text-sm text-error"
              data-testid="courier-custody-machine"
            >
              {{ machinesOutSentence(equipmentOptions ?? []) }} Espere uma
              voltar para chamar.
            </p>
          </template>
        </div>
        <div class="flex flex-wrap gap-2">
          <NuxtButton
            v-if="courier.can_dispatch"
            type="button"
            :disabled="
              busy ||
              !dispatchAction?.enabled ||
              (confirmingDispatch && machineMissing)
            "
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
              confirmingDispatch
                ? 'Confirmar chamada'
                : hasRide || courier.attempts_count > 0
                  ? 'Chamar outro entregador'
                  : 'Chamar entregador'
            "
            @blur="blurDispatch"
            @click="requestDispatch"
          />
          <NuxtButton
            v-if="confirmingDispatch && asksCustody"
            type="button"
            label="Voltar"
            color="neutral"
            variant="outline"
            @click="confirmingDispatch = false"
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
    </div>
  </NuxtCard>
</template>
