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
import type { ChannelSwitchProjection, ManagerOptionProjection } from "~/types/feeds";
import type { ChannelSwitchOutcome, ChannelSwitchRequest } from "~/composables/useFeedBoard";
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
  submit: (request: ChannelSwitchRequest, approval?: Record<string, string>) => Promise<ChannelSwitchOutcome>;
  /** Relógio injetável (retratos e testes). */
  now?: Date;
}>();
const emit = defineEmits<{ "update:open": [boolean] }>();

const draft = ref(emptyDraft());
const managerOpen = ref(false);
const managerError = ref("");
const failure = ref("");

watch(() => props.open, (open) => {
  if (!open) return;
  draft.value = emptyDraft();
  managerOpen.value = false;
  managerError.value = "";
  failure.value = "";
});

const clock = computed(() => props.now ?? new Date());
const missing = computed(() => (props.sw ? missingStep(props.sw, draft.value, clock.value) : ""));
const label = computed(() => (props.sw ? confirmLabel(props.sw, draft.value, clock.value) : ""));
const turningOff = computed(() => Boolean(props.sw?.is_active));

function pickReason(reason: string) {
  draft.value = { ...draft.value, reason: draft.value.reason === reason ? "" : reason };
}

async function send(approval?: Record<string, string>) {
  if (!props.sw || missing.value || props.busy) return;
  failure.value = "";
  const outcome = await props.submit(switchRequest(props.sw, draft.value), approval);
  if (outcome.ok) {
    managerOpen.value = false;
    emit("update:open", false);
    return;
  }
  if (outcome.code === "manager_approval_required" || outcome.code === "manager_approval_invalid") {
    managerOpen.value = true;
    managerError.value = outcome.code === "manager_approval_invalid" ? outcome.message : "";
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
  <UiDialog :open="open && !managerOpen" @update:open="close">
    <UiDialogContent v-if="sw" class="max-h-[90dvh] overflow-y-auto sm:max-w-lg" data-channel-switch-dialog>
      <UiDialogHeader>
        <UiDialogTitle>{{ sw.title }}</UiDialogTitle>
        <UiDialogDescription>{{ sw.consequence }}</UiDialogDescription>
      </UiDialogHeader>

      <p v-if="sw.scheduled_line" class="rounded-md border border-warning/50 bg-warning/10 px-3 py-2 text-sm" data-switch-replaces>
        Substitui o agendamento: {{ sw.scheduled_line }}
      </p>

      <fieldset class="flex flex-col gap-1.5">
        <legend class="mb-1 text-sm font-medium">Por quanto tempo</legend>
        <label
          v-for="option in sw.periods"
          :key="option.key"
          class="flex min-h-control items-start gap-2 rounded-md border px-3 py-2 text-sm"
          :class="option.enabled ? 'cursor-pointer hover:bg-accent' : 'opacity-60'"
          :data-period="option.key"
        >
          <input
            v-model="draft.period" type="radio" name="channel-switch-period" class="mt-1"
            :value="option.key" :disabled="!option.enabled"
          >
          <span class="flex flex-col">
            <span>{{ option.label }}</span>
            <span v-if="!option.enabled && option.reason" class="text-xs text-muted-foreground">{{ option.reason }}</span>
          </span>
        </label>
      </fieldset>

      <ChannelPeriodCalendar v-if="draft.period === CUSTOM_PERIOD" v-model="draft" :today="clock" />
      <p v-if="!turningOff" class="text-xs text-muted-foreground" data-switch-shop-hours>
        Ligado, o canal só recebe pedidos dentro do horário da loja.
      </p>

      <div class="flex flex-col gap-1.5">
        <span class="text-sm font-medium">Motivo<span v-if="!sw.reason_required" class="font-normal text-muted-foreground"> (opcional)</span></span>
        <div v-if="sw.reasons.length" class="flex flex-wrap gap-1.5">
          <button
            v-for="preset in sw.reasons"
            :key="preset"
            type="button"
            :aria-pressed="draft.reason === preset"
            class="min-h-control min-w-control rounded-full border px-3 py-1 text-xs font-medium transition hover:bg-accent"
            :class="draft.reason === preset ? 'border-primary bg-primary/10 text-primary' : 'text-muted-foreground'"
            @click="pickReason(preset)"
          >
            {{ preset }}
          </button>
        </div>
        <textarea
          v-model="draft.reason"
          rows="2"
          maxlength="200"
          :placeholder="sw.reasons.length ? 'Ou escreva o motivo…' : 'Escreva o motivo, se quiser…'"
          class="min-h-control w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Motivo"
        />
      </div>

      <p v-if="failure" role="alert" class="text-sm text-destructive" data-switch-failure>{{ failure }}</p>

      <UiDialogFooter class="items-center gap-2">
        <p v-if="missing" class="mr-auto text-xs text-muted-foreground" data-switch-missing>{{ missing }}</p>
        <p v-else-if="sw.requires_manager_approval" class="mr-auto text-xs text-muted-foreground">Um gerente autoriza no próximo passo.</p>
        <button
          type="button" :disabled="busy"
          class="min-h-control min-w-control rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
          @click="close(false)"
        >
          Voltar
        </button>
        <button
          type="button"
          :disabled="busy || Boolean(missing)"
          class="min-h-action min-w-action rounded-md border border-transparent px-3 py-2 text-sm font-semibold transition disabled:opacity-50"
          :class="turningOff ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90' : 'bg-primary text-primary-foreground hover:bg-primary/90'"
          data-switch-confirm
          @click="confirm"
        >
          {{ label }}
        </button>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>

  <OperatorManagerAuth
    :open="open && managerOpen"
    :action="turningOff ? 'channel_off' : 'channel_on'"
    :operator-name="viewerName"
    :managers="managers"
    :busy="busy"
    :error="managerError"
    @update:open="(value: boolean) => { if (!value && !busy) managerOpen = false; }"
    @authorize="(username: string, pin: string) => send({ username, pin })"
    @authorize-badge="(badge: string) => send({ badge })"
  />
</template>
