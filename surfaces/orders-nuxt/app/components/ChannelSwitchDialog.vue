<script setup lang="ts">
// O modal do toggle "Ativo" — UM só para todo card da aba Canais (loja online,
// WhatsApp, iFood, PDV, TV, feeds). Mexer no toggle, para desligar OU para ligar,
// abre este modal, que faz três coisas:
//
//   1. o PERÍODO: 30 min, 1 hora, hoje, sem prazo, ou um período no calendário. No
//      fim do período o canal volta sozinho ao estado de antes. As opções vêm do
//      servidor já filtradas pelo horário da loja: ligar nunca abre fora dele;
//   2. o MOTIVO: os recorrentes do tipo de canal + campo livre (obrigatório para
//      desligar);
//   3. a AUTORIZAÇÃO do gerente, no mesmo diálogo do PDV (`OperatorManagerAuth`):
//      gerente logado só confirma; quem não é, chama um gerente (crachá ou PIN).
//
// A pausa do iFood (#950) era um modal à parte com prazo e motivo; ela é este
// modal, com o iFood como mais um canal.
import type {
  ChannelSwitchProjection,
  ManagerOptionProjection,
} from "~/types/feeds";
import type {
  ChannelSwitchOutcome,
  ChannelSwitchRequest,
} from "~/composables/useFeedBoard";
import {
  CUSTOM_PERIOD,
  confirmLabel,
  emptyDraft,
  missingStep,
  switchRequest,
} from "~/presentation/channelSwitch";

const props = defineProps<{
  open: boolean;
  sw: ChannelSwitchProjection | null;
  managers: ManagerOptionProjection[];
  viewerName: string;
  busy: boolean;
  submit: (
    request: ChannelSwitchRequest,
    approval?: Record<string, string>,
  ) => Promise<ChannelSwitchOutcome>;
  /** Relógio injetável (retratos e testes). */
  now?: Date;
}>();
const emit = defineEmits<{ "update:open": [boolean] }>();

const draft = ref(emptyDraft());
const managerOpen = ref(false);
const managerError = ref("");
const failure = ref("");

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    draft.value = emptyDraft();
    managerOpen.value = false;
    managerError.value = "";
    failure.value = "";
  },
);

const clock = computed(() => props.now ?? new Date());
const missing = computed(() =>
  props.sw ? missingStep(props.sw, draft.value, clock.value) : "",
);
const label = computed(() =>
  props.sw ? confirmLabel(props.sw, draft.value, clock.value) : "",
);
const turningOff = computed(() => Boolean(props.sw?.is_active));

async function send(approval?: Record<string, string>) {
  if (!props.sw || missing.value || props.busy) return;
  failure.value = "";
  const outcome = await props.submit(
    switchRequest(props.sw, draft.value),
    approval,
  );
  if (outcome.ok) {
    managerOpen.value = false;
    emit("update:open", false);
    return;
  }
  if (
    outcome.code === "manager_approval_required" ||
    outcome.code === "manager_approval_invalid"
  ) {
    managerOpen.value = true;
    managerError.value =
      outcome.code === "manager_approval_invalid" ? outcome.message : "";
    return;
  }
  managerOpen.value = false;
  failure.value = outcome.message;
}

function confirm() {
  if (!props.sw || missing.value) return;
  if (props.sw.requires_manager_approval) {
    managerError.value = "";
    managerOpen.value = true;
    return;
  }
  send();
}

function close(value: boolean) {
  if (!value && !props.busy) emit("update:open", false);
}
</script>

<template>
  <NuxtModal
    v-if="sw"
    :open="open && !managerOpen"
    :title="sw.title"
    :description="sw.consequence"
    scrollable
    data-channel-switch-dialog
    @update:open="close"
  >
    <template #body>
      <div class="grid gap-4">
        <NuxtAlert
          v-if="sw.scheduled_line"
          color="warning"
          variant="subtle"
          icon="i-lucide-calendar-clock"
          title="Substitui o agendamento"
          :description="sw.scheduled_line"
          data-switch-replaces
        />

        <NuxtFormField label="Por quanto tempo">
          <NuxtRadioGroup
            v-model="draft.period"
            :items="
              sw.periods.map((option) => ({
                value: option.key,
                label: option.label,
                description: !option.enabled ? option.reason : undefined,
                disabled: !option.enabled,
                'data-period': option.key,
              }))
            "
            variant="card"
          />
        </NuxtFormField>

        <ChannelPeriodCalendar
          v-if="draft.period === CUSTOM_PERIOD"
          v-model="draft"
          :today="clock"
        />
        <p
          v-if="!turningOff"
          class="text-xs text-muted-foreground"
          data-switch-shop-hours
        >
          Ligado, o canal só recebe pedidos dentro do horário da loja.
        </p>

        <NuxtFormField
          label="Motivo"
          :hint="sw.reason_required ? undefined : 'opcional'"
        >
          <NuxtRadioGroup
            v-if="sw.reasons.length"
            v-model="draft.reason"
            :items="sw.reasons"
            variant="card"
          />
          <NuxtTextarea
            v-model="draft.reason"
            class="w-full"
            :rows="2"
            maxlength="200"
            :placeholder="
              sw.reasons.length
                ? 'Ou escreva o motivo…'
                : 'Escreva o motivo, se quiser…'
            "
            aria-label="Motivo"
          />
        </NuxtFormField>

        <NuxtAlert
          v-if="failure"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :title="failure"
          data-switch-failure
        />
      </div>
    </template>
    <template #footer>
      <p
        v-if="missing"
        class="me-auto text-xs text-muted-foreground"
        data-switch-missing
      >
        {{ missing }}
      </p>
      <p
        v-else-if="sw.requires_manager_approval"
        class="me-auto text-xs text-muted-foreground"
      >
        Um gerente autoriza no próximo passo.
      </p>
      <NuxtButton
        label="Voltar"
        color="neutral"
        variant="outline"
        :disabled="busy"
        @click="close(false)"
      />
      <NuxtButton
        :label="label"
        :color="turningOff ? 'error' : 'primary'"
        :disabled="busy || Boolean(missing)"
        :loading="busy"
        data-switch-confirm
        @click="confirm"
      />
    </template>
  </NuxtModal>

  <OperatorManagerAuth
    :open="open && managerOpen"
    :action="turningOff ? 'channel_off' : 'channel_on'"
    :operator-name="viewerName"
    :managers="managers"
    :busy="busy"
    :error="managerError"
    @update:open="
      (value: boolean) => {
        if (!value && !busy) managerOpen = false;
      }
    "
    @authorize="(username: string, pin: string) => send({ username, pin })"
    @authorize-badge="(badge: string) => send({ badge })"
  />
</template>
