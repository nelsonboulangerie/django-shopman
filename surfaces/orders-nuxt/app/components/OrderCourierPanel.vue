<script setup lang="ts">
// Courier ride panel — the operator's window into the external delivery
// (Machine): compact step timeline, driver card, tracking link, quoted cost,
// and the ride actions (quote / dispatch / cancel). Status text comes from the
// server projection; steps/tones are derived from the raw letter.
import {
  courierFailed,
  courierReminderLine,
  courierSteps,
  courierTone,
} from "~/presentation/courier";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";
import type { Action, EquipmentOptionProjection } from "~/generated/ordersContract";
import type { CourierBlock } from "~/types/orders";
import { courierCancelNotice } from "../../../operator-kit/app/presentation/courierCancel";
import { courierProgress } from "../../../operator-kit/app/presentation/courierProgress";
import { courierChargeNotice } from "../../../operator-kit/app/presentation/courierCharge";
import { freeMachines, machinePhrase, moneyInput } from "../../../operator-kit/app/presentation/custody";

const props = defineProps<{
  courier: CourierBlock;
  busy: boolean;
  cancelAction?: Action;
  quoteAction?: Action;
  dispatchAction?: Action;
  dispatchAgainAction?: Action;
  /** O sheet de chamar está abrindo (a página lê as Entregas). */
  calling?: boolean;
  /** A cotação está a caminho (o toque em "Cotar entrega" ainda não voltou). */
  quoting?: boolean;
  /** A última cotação falhou: a frase do servidor, ou vazio. */
  quoteError?: string;
  /** "Separar de novo" (`courier-custody`, #2500) e as maquininhas do pedido. */
  custodyAction?: Action;
  equipmentOptions?: EquipmentOptionProjection[];
}>();
const emit = defineEmits<{
  quote: [];
  /** Abrir o sheet de chamar (`CourierCallSheet`), o mesmo das Entregas. */
  call: [];
  /** Confirmado: depois do aceite vem com o motivo escolhido (`reason_id` da TaOn). */
  cancel: [reasonId?: number];
  dispatchAgain: [];
  dismissReminder: [];
  dismissQuoteError: [];
  /** "Separar de novo": o troco e a maquininha da corrida retomada. */
  separate: [body: { change_out?: string; equipment?: string[] }];
}>();

const steps = computed(() => courierSteps(props.courier.ride_state));
const tone = computed(() => courierTone(props.courier.ride_state));
const failed = computed(() => courierFailed(props.courier.ride_state));
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

// Cancelar corrida é irreversível para a solicitação em curso: o primeiro toque
// só ARMA a confirmação (`CourierCancelConfirm`, a mesma da seção Entregas); o
// segundo confirma e, depois do aceite, já é o motivo. Um toque nunca cancela.
const confirmingCancel = ref(false);
watch(
  () => JSON.stringify(props.cancelAction?.payload_schema),
  () => {
    confirmingCancel.value = false;
  },
);
function requestCancel() {
  confirmingCancel.value = true;
}
function confirmCancel(reasonId?: number) {
  confirmingCancel.value = false;
  emit("cancel", reasonId);
}

// O cancelamento pedido (`courier.cancel_state`): espera, dúvida ou recusa da
// TaOn. Dispensável, e volta quando o estado muda (a recusa não é a espera).
const cancelState = computed(() =>
  courierCancelNotice(
    props.courier.cancel_state?.state,
    props.courier.cancel_state?.message,
  ),
);
const cancelDismissedFor = ref("");
const cancelStateKey = computed(
  () =>
    `${props.courier.cancel_state?.state ?? ""}:${props.courier.cancel_state?.at ?? ""}`,
);
const showCancelState = computed(
  () =>
    Boolean(cancelState.value) &&
    cancelDismissedFor.value !== cancelStateKey.value,
);

// O pedido mudou depois da chamada e a corrida leva a cobrança antiga (P2-28): o
// aviso amarelo leva o "Cancelar corrida", que arma a MESMA confirmação de baixo;
// cancelada a corrida, o "Chamar entregador" de sempre leva a cobrança nova.
const chargeNotice = computed(() =>
  courierChargeNotice(props.courier.charge_outdated, { cancelHere: true }),
);
// O aviso leva o gesto: o botão de baixo só volta para confirmar (um lugar só).
const chargeOffersCancel = computed(
  () =>
    Boolean(chargeNotice.value) &&
    props.courier.can_cancel &&
    !props.courier.charge_outdated?.collected,
);
const chargeActions = computed(() => [
  chargeOffersCancel.value &&
    !confirmingCancel.value && {
      label: props.cancelAction?.label || "Cancelar corrida",
      icon: "i-lucide-ban",
      disabled: props.busy || !props.cancelAction?.enabled,
      onClick: requestCancel,
      ...{ "data-courier-charge-cancel": "" },
    },
]);

// A TaOn retomou a corrida encerrada (#2500): o troco e a maquininha tinham
// voltado para a casa. O aviso diz o que voltou e leva o "Separar de novo", que
// abre aqui o troco (já com o valor da chamada) e a maquininha livre.
const toSeparate = computed(() => props.courier.custody_to_separate ?? null);
const separateWhat = computed(() => {
  const missing = toSeparate.value;
  if (!missing) return "";
  const parts = [missing.change_out_suggested_q > 0 && "O troco", missing.needs_machine && "a maquininha"].filter(Boolean);
  return parts.length === 2 ? "O troco e a maquininha voltaram" : `${parts[0] === "O troco" ? "O troco" : "A maquininha"} voltou`;
});
const separating = ref(false);
const separateChange = ref("");
const separateMachines = computed(() => freeMachines(props.equipmentOptions ?? []));
const separateMachine = ref("");
watch(
  toSeparate,
  (missing) => {
    separating.value = false;
    separateChange.value = missing ? moneyInput(missing.change_out_suggested_q) : "";
    separateMachine.value = "";
  },
  { immediate: true },
);
watch(separateMachines, (free) => {
  if (!free.some((option) => option.ref === separateMachine.value)) separateMachine.value = free[0]?.ref ?? "";
}, { immediate: true });
const separateBlocked = computed(
  () => Boolean(toSeparate.value?.needs_machine) && !separateMachine.value,
);
const separateActions = computed(() => [
  !separating.value && {
    label: props.custodyAction?.label || "Separar de novo",
    icon: "i-lucide-hand-coins",
    disabled: props.busy || !props.custodyAction?.enabled,
    onClick: () => {
      separating.value = true;
    },
    ...{ "data-courier-separate": "" },
  },
]);
// Gesto de dinheiro: o rótulo diz tudo o que sai ("Separar R$ 26,00 e a maquininha Azul").
const separateLabel = computed(() => {
  const missing = toSeparate.value;
  const money = missing && missing.change_out_suggested_q > 0 && separateChange.value.trim()
    ? `R$ ${separateChange.value.trim()}` : "";
  const label = separateMachines.value.find((option) => option.ref === separateMachine.value)?.label ?? "";
  const machine = missing?.needs_machine && separateMachine.value ? `a ${machinePhrase(label)}` : "";
  const parts = [money, machine].filter(Boolean);
  return parts.length ? `Separar ${parts.join(" e ")}` : "Separar";
});
function confirmSeparate() {
  if (separateBlocked.value) return;
  const missing = toSeparate.value;
  emit("separate", {
    ...(missing && missing.change_out_suggested_q > 0 ? { change_out: separateChange.value } : {}),
    ...(missing?.needs_machine && separateMachine.value ? { equipment: [separateMachine.value] } : {}),
  });
}

// Chamar entregador abre o MESMO sheet das Entregas (`CourierCallSheet`, #2876): a
// página é dona dele (custódia, quem vai junto, cotação da sugestão). Aqui o toque só
// pede para abrir; um toque nunca chama.
function requestDispatch() {
  if (props.busy || props.calling || !props.dispatchAction?.enabled) return;
  emit("call");
}

// Lembrete temporário (entrega da casa em preparo há X min, sem entregador chamado):
// o aviso amarelo leva o "Chamar entregador", que abre o MESMO sheet de chamar.
const nowMs = useNowTick();
const reminderLine = computed(() =>
  props.courier.can_dispatch
    ? courierReminderLine(props.courier.reminder, nowMs.value)
    : null,
);
const reminderActions = computed(() => [
  {
    label: "Chamar entregador",
    icon: "i-lucide-bike",
    disabled: props.busy || props.calling || !props.dispatchAction?.enabled,
    onClick: requestDispatch,
    ...{ "data-courier-reminder-call": "" },
  },
  {
    label: "Dispensar",
    disabled: props.busy,
    onClick: () => emit("dismissReminder"),
    ...{ "data-courier-reminder-dismiss": "" },
  },
]);

// A cotação antes da corrida: valor, tempo e distância numa linha forte, com o
// "Chamar entregador" logo abaixo como a ação do momento. Com corrida aberta, o
// valor volta ao cabeçalho (é o custo dela, não uma proposta).
const quoteValue = computed(() =>
  props.quoting ? "Cotando a entrega…" : props.courier.estimate_display,
);
const showQuote = computed(
  () => !hasRide.value && (props.quoting || Boolean(props.courier.estimate_display)),
);
const quoteActions = computed(() => [
  {
    label: "Cotar de novo",
    icon: "i-lucide-refresh-cw",
    disabled: props.busy || !props.quoteAction?.enabled,
    onClick: () => emit("quote"),
    ...{ "data-courier-quote-retry": "" },
  },
]);

const telHref = (phone: string) => `tel:${phone.replace(/[^\d+]/g, "")}`;

// O andamento (chega para coletar, entrega prevista) anda com o relógio da
// tela entre uma leitura e outra; a leitura nova chega por SSE.
const progress = computed(() => courierProgress(props.courier, nowMs.value));
// "Sem notícias da TaOn" se dispensa, e volta se a falha recomeçar.
const staleDismissedFor = ref("");
const showStale = computed(
  () =>
    Boolean(progress.value.stale) &&
    staleDismissedFor.value !== (props.courier.sync_since ?? ""),
);
const vehicle = computed(() =>
  [
    props.courier.driver?.vehicle_model,
    props.courier.driver?.vehicle_color,
    props.courier.driver?.vehicle_plate,
  ]
    .filter(Boolean)
    .join(" · "),
);
</script>

<template>
  <NuxtCard id="courier-call" as="section" class="scroll-mt-20">
    <div class="flex flex-col gap-3">
      <div class="flex flex-wrap items-center gap-2">
        <h2 class="flex items-center gap-1.5 op-title">
          <Icon name="lucide:bike" class="size-4" /> Entregador
        </h2>
        <!-- Com o aviso de "não respondeu" na tela, o selo sai: ele dizia o mesmo
             assunto logo acima do aviso ("Sem resposta da TaOn"). Um lugar só. -->
        <NuxtBadge
          v-if="courier.status_label && !courier.can_dispatch_again"
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
          v-if="
            hasRide && (courier.final_value_display || courier.estimate_display)
          "
          class="ms-auto text-sm tabular-nums text-muted-foreground"
        >
          {{ courier.final_value_display || courier.estimate_display }}
        </span>
      </div>

      <!-- o andamento: quando chega para coletar e quando a entrega está prevista -->
      <div
        v-if="progress.waiting || progress.pickup || progress.delivery"
        class="flex flex-col gap-0.5"
        data-testid="courier-progress"
      >
        <!-- o entregador desistiu (a TaOn redistribui a mesma corrida) ou a TaOn
             juntou com outra: a corrida segue chamada, sem nada a fazer -->
        <p
          v-if="progress.waiting"
          class="font-medium tabular-nums"
          role="status"
          data-testid="courier-waiting"
        >
          {{ progress.waiting }}
        </p>
        <p
          v-if="progress.pickup"
          class="font-medium tabular-nums"
          role="status"
        >
          {{ progress.pickup }}
        </p>
        <!-- Depois da coleta a entrega prevista é a linha principal. -->
        <p
          v-if="progress.delivery"
          class="tabular-nums"
          :class="
            progress.pickup ? 'text-sm text-muted-foreground' : 'font-medium'
          "
        >
          {{ progress.delivery }}
        </p>
      </div>

      <div class="flex flex-col gap-3">
        <!-- a TaOn parou de informar a corrida: o que está na tela pode estar parado -->
        <NuxtAlert
          v-if="showStale"
          color="warning"
          variant="subtle"
          icon="i-lucide-cloud-off"
          :title="progress.stale"
          description="O status na tela pode estar parado. Confira no painel da TaOn."
          close
          data-testid="courier-stale"
          @update:open="staleDismissedFor = courier.sync_since ?? ''"
        />

        <!-- lembrete: já dá para chamar o entregador? -->
        <NuxtAlert
          v-if="reminderLine"
          color="warning"
          variant="subtle"
          icon="i-lucide-bike"
          :title="reminderLine"
          :actions="alertActions('warning', reminderActions)"
          role="status"
          data-courier-reminder
        />

        <!-- a TaOn não respondeu à última chamada: só ela trava chamar outra. É
             cautela (a corrida pode ter aberto), não erro da casa: tom de atenção, e
             o botão acompanha a cor do aviso. -->
        <NuxtAlert
          v-if="courier.can_dispatch_again"
          color="warning"
          variant="subtle"
          icon="i-lucide-circle-help"
          :title="
            courier.error?.message || 'A TaOn não respondeu à última chamada.'
          "
          data-courier-no-answer
        >
          <template #actions>
            <NuxtButton
              type="button"
              color="warning"
              variant="outline"
              icon="i-lucide-refresh-cw"
              label="Chamar de novo"
              :disabled="busy || !dispatchAgainAction?.enabled"
              :title="dispatchAgainAction?.reason || ''"
              @click="emit('dispatchAgain')"
            />
          </template>
        </NuxtAlert>

        <!-- o cancelamento pedido: esperando a TaOn, sem resposta, ou recusado -->
        <NuxtAlert
          v-if="showCancelState && cancelState"
          :color="cancelState.color"
          variant="subtle"
          :icon="cancelState.icon"
          :title="cancelState.message"
          close
          role="status"
          data-courier-cancel-state
          @update:open="cancelDismissedFor = cancelStateKey"
        />

        <!-- falha terminal do despacho (Machine recusou / dados) -->
        <NuxtAlert
          v-else-if="courier.error"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          title="Falha ao abrir a corrida"
          :description="courier.error.message"
        />

        <!-- a TaOn retomou a corrida encerrada: separar de novo o que voltou (#2500) -->
        <NuxtAlert
          v-if="toSeparate"
          color="warning"
          variant="subtle"
          icon="i-lucide-hand-coins"
          :title="`${separateWhat} para a casa`"
          :description="`A ${courier.service_name || 'central'} retomou a corrida. Separe de novo antes de entregar a sacola.`"
          :actions="alertActions('warning', separateActions)"
          role="status"
          data-courier-custody-missing
        />
        <div v-if="toSeparate && separating" class="flex flex-col gap-3 rounded-lg border border-default p-3" data-courier-separate-form>
          <NuxtFormField v-if="toSeparate.change_out_suggested_q > 0" label="Troco a levar" name="change_out">
            <NuxtInput v-model="separateChange" inputmode="decimal" class="w-40" :ui="{ base: 'min-h-11' }" data-courier-separate-change>
              <template #leading><span class="text-muted">R$</span></template>
            </NuxtInput>
          </NuxtFormField>
          <NuxtFormField v-if="toSeparate.needs_machine" label="Maquininha" name="equipment">
            <NuxtSelect
              v-if="separateMachines.length"
              v-model="separateMachine"
              :items="separateMachines.map((option) => ({ value: option.ref, label: option.label }))"
              class="w-60"
              :ui="{ base: 'min-h-11' }"
              data-courier-separate-machine
            />
            <p v-else class="text-sm text-error" data-courier-separate-no-machine>
              Nenhuma maquininha livre agora. Receba uma de volta antes de separar.
            </p>
          </NuxtFormField>
          <div class="flex flex-wrap gap-2">
            <NuxtButton
              type="button"
              color="primary"
              icon="i-lucide-check"
              :label="separateLabel"
              :disabled="busy || separateBlocked || !custodyAction?.enabled"
              :loading="busy"
              class="min-h-11"
              data-courier-separate-go
              @click="confirmSeparate"
            />
            <NuxtButton
              type="button"
              color="neutral"
              variant="outline"
              label="Agora não"
              class="min-h-11"
              data-courier-separate-keep
              @click="separating = false"
            />
          </div>
        </div>

        <!-- o pedido mudou depois da chamada: a corrida leva a cobrança antiga -->
        <NuxtAlert
          v-if="chargeNotice"
          color="warning"
          variant="subtle"
          icon="i-lucide-receipt-text"
          :title="chargeNotice.title"
          :description="chargeNotice.description"
          :actions="alertActions('warning', chargeActions)"
          role="status"
          data-courier-charge-outdated
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
        <!-- A foto da TaOn enquanto a corrida vive, a mesma da página Entregas (#2736). -->
        <NuxtAlert
          v-if="courier.driver?.name"
          color="info"
          variant="subtle"
          :icon="courier.driver.photo_url ? undefined : 'i-lucide-user'"
          :avatar="courier.driver.photo_url ? { src: courier.driver.photo_url, alt: courier.driver.name, size: 'lg' } : undefined"
          :title="courier.driver.name"
          data-order-courier-driver
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
                v-if="vehicle"
                class="flex items-center gap-1.5 text-muted-foreground"
              >
                <Icon name="lucide:bike" class="size-4" />
                {{ vehicle }}
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
            <strong class="tabular-nums">{{
              courier.confirmation_code
            }}</strong>
          </span>
        </div>
      </div>

      <!-- a cotação falhou: aviso com a ação na cor dele, e dispensável -->
      <NuxtAlert
        v-if="quoteError && !quoting"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Não deu para cotar a entrega"
        :description="quoteError"
        :actions="alertActions('error', quoteActions)"
        close
        data-courier-quote-error
        @update:open="emit('dismissQuoteError')"
      />

      <!-- a cotação: o resultado em destaque, e a chamada logo abaixo -->
      <NuxtCard
        v-if="showQuote"
        variant="soft"
        data-courier-quote
        :aria-busy="quoting || undefined"
      >
        <div class="flex flex-col items-center gap-1 text-center">
          <p class="text-xs text-muted-foreground">Cotação da entrega</p>
          <p
            v-if="quoteValue"
            class="text-lg font-semibold tabular-nums"
            role="status"
            data-courier-quote-value
          >
            {{ quoteValue }}
          </p>
        </div>
      </NuxtCard>

      <template
        v-if="courier.can_quote || courier.can_dispatch || courier.can_cancel"
      >
        <div
          class="flex flex-wrap gap-2"
          :class="showQuote ? 'justify-center' : ''"
        >
          <!-- Abre o sheet de chamar (o mesmo das Entregas): troco, maquininha e quem
               vai junto se conferem lá. Com o lembrete na tela, o gesto mora nele. -->
          <NuxtButton
            v-if="courier.can_dispatch && !reminderLine"
            type="button"
            :loading="calling"
            :disabled="busy || calling || !dispatchAction?.enabled"
            :title="
              dispatchAction?.reason ||
              (dispatchAction?.enabled
                ? ''
                : 'Atualize o pedido para conferir esta ação.')
            "
            :icon="
              hasRide || courier.attempts_count > 0
                ? 'i-lucide-refresh-cw'
                : 'i-lucide-bike'
            "
            :label="
              hasRide || courier.attempts_count > 0
                ? 'Chamar outro entregador'
                : 'Chamar entregador'
            "
            data-courier-call
            @click="requestDispatch"
          />
          <NuxtButton
            v-if="courier.can_quote && !(quoteError && !quoting)"
            type="button"
            :loading="quoting"
            :disabled="busy || quoting || !quoteAction?.enabled"
            :title="
              quoteAction?.reason ||
              (quoteAction?.enabled
                ? ''
                : 'Atualize o pedido para conferir esta ação.')
            "
            icon="i-lucide-calculator"
            :label="
              courier.estimate_display ? 'Cotar de novo' : 'Cotar entrega'
            "
            data-courier-quote-button
            color="neutral"
            variant="outline"
            @click="emit('quote')"
          />
          <NuxtButton
            v-if="courier.can_cancel && !chargeOffersCancel && !confirmingCancel"
            type="button"
            :disabled="busy || !cancelAction?.enabled"
            :title="cancelAction?.reason || undefined"
            icon="i-lucide-ban"
            :label="cancelAction?.label || 'Cancelar corrida'"
            color="error"
            variant="outline"
            data-courier-cancel
            @click="requestCancel"
          />
        </div>
        <CourierCancelConfirm
          v-if="courier.can_cancel && confirmingCancel && cancelAction"
          :action="cancelAction"
          :busy="busy"
          @confirm="confirmCancel"
          @keep="confirmingCancel = false"
        />
      </template>
    </div>
  </NuxtCard>
</template>
