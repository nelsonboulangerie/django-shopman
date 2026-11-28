<script setup lang="ts">
// Operator changes their own PIN on a stepped pad: current → new → confirm.
// Proving the current PIN is the authorization (enforced by the backend). Used
// voluntarily from the lock screen and forced after a manager reset (must-change).
// Pure UI — the parent owns the network call (changePin) and passes busy/error.
import { PIN_DIGITS, PIN_MIN_DIGITS, appendPinDigit } from "../presentation/operatorLock";
import { alertActions } from "../utils/alertActions";

const props = defineProps<{
  operatorName: string;
  forced?: boolean;
  busy?: boolean;
  error?: string;
  /** Na troca forçada: onde o gerente redefine o PIN (o Admin, Credenciais PIN). */
  resetHref?: string;
}>();

const emit = defineEmits<{
  submit: [{ currentPin: string; newPin: string }];
  cancel: [];
  /** Na troca forçada: "Não é você?" (quem pede encerra a sessão). */
  switchUser: [];
}>();

// Na troca forçada a pessoa precisa saber DE QUEM é o PIN e ter saída (P0 de
// 23/11, depois do #3337): a sessão pode ser de outra conta, e sem isto a tela
// prendia quem não sabia o PIN dela.
const forgot = ref(false);

type Step = "current" | "new" | "confirm";
const step = ref<Step>("current");
const currentPin = ref("");
const newPin = ref("");
const confirmPin = ref("");
const localError = ref("");

const label = computed(() => {
  // Forçada ou não, o primeiro passo é o PIN com que a pessoa entra hoje: o
  // temporário do gerente ou o antigo, de antes dos 4 dígitos fixos (#3223).
  if (step.value === "current") return "PIN atual";
  if (step.value === "new") return "Novo PIN";
  return "Repita o novo PIN";
});

function activeValue(): string {
  if (step.value === "current") return currentPin.value;
  if (step.value === "new") return newPin.value;
  return confirmPin.value;
}
function setActive(v: string) {
  if (step.value === "current") currentPin.value = v;
  else if (step.value === "new") newPin.value = v;
  else confirmPin.value = v;
}

// O PIN atual pode ser o antigo, de 4 a 8 dígitos. O NOVO tem exatamente 4
// (#3223, decisão do dono): o campo para no quarto, e o servidor recusa o resto.
const newStep = computed(() => step.value !== "current");
const canAdvance = computed(() =>
  newStep.value
    ? activeValue().trim().length === PIN_DIGITS
    : activeValue().trim().length >= PIN_MIN_DIGITS,
);

function press(d: string) {
  localError.value = "";
  setActive(newStep.value ? appendPinDigit(activeValue(), d, PIN_DIGITS) : appendPinDigit(activeValue(), d));
}
function backspace() {
  setActive(activeValue().slice(0, -1));
}
function advance() {
  if (!canAdvance.value || props.busy) return;
  localError.value = "";
  if (step.value === "current") {
    step.value = "new";
    return;
  }
  if (step.value === "new") {
    // Trocar pelo mesmo PIN não é troca (beta 05/11, PDV-26). O servidor também
    // recusa; aqui a pessoa sabe antes de repetir o PIN à toa.
    if (newPin.value.trim() === currentPin.value.trim()) {
      localError.value = "Escolha um PIN diferente do atual.";
      newPin.value = "";
      return;
    }
    step.value = "confirm";
    return;
  }
  if (newPin.value.trim() !== confirmPin.value.trim()) {
    localError.value = "Os PINs não conferem. Tente de novo.";
    confirmPin.value = "";
    return;
  }
  emit("submit", {
    currentPin: currentPin.value.trim(),
    newPin: newPin.value.trim(),
  });
}

function back() {
  localError.value = "";
  if (step.value === "confirm") {
    step.value = "new";
    confirmPin.value = "";
    return;
  }
  if (step.value === "new") {
    step.value = "current";
    newPin.value = "";
    return;
  }
  emit("cancel");
}

const shownError = computed(() => localError.value || props.error || "");
</script>

<template>
  <div class="grid gap-5 [@media(max-height:43.75rem)]:gap-3">
    <!-- Mesmo cabeçalho da trava (cadeado → chave): centrado, título e a
         linha que diz o que fazer. -->
    <header class="grid justify-items-center gap-3 text-center">
      <NuxtAvatar size="3xl" icon="i-lucide-key-round" alt="" class="[@media(max-height:43.75rem)]:hidden" />
      <div class="grid gap-1">
        <h2 class="text-lg font-semibold">
          {{ forced ? "Defina um novo PIN" : "Trocar meu PIN" }}
        </h2>
        <p class="text-sm text-muted-foreground">
          {{
            forced
              ? `${operatorName}, seu PIN precisa ser trocado antes de operar. Digite o PIN atual e escolha um novo, de 4 dígitos.`
              : `${operatorName}, informe o PIN atual e escolha um novo, de 4 dígitos.`
          }}
        </p>
      </div>
    </header>

    <OperatorPinPad
      :key="step"
      :pin="activeValue()"
      :label="label"
      :error="shownError"
      :can-submit="canAdvance"
      :busy="busy"
      :fixed-digits="newStep ? PIN_DIGITS : null"
      :submit-icon="step === 'confirm' ? 'i-lucide-check' : 'i-lucide-arrow-right'"
      :submit-label="step === 'confirm' ? 'Confirmar o novo PIN' : 'Continuar'"
      keyboard
      @digit="press"
      @backspace="backspace"
      @submit="advance"
    />

    <!-- Na troca forçada não há o que cancelar no primeiro passo: sem PIN novo
         não se opera, e um "Cancelar" que não faz nada mentiria. -->
    <div v-if="!(forced && step === 'current')" class="flex justify-center">
      <NuxtButton
        color="neutral"
        variant="ghost"
        icon="i-lucide-chevron-left"
        :label="step === 'current' ? 'Cancelar' : 'Voltar'"
        @click="back"
      />
    </div>

    <!-- Troca forçada: sempre há saída. Outra pessoa entra no lugar, ou quem não
         lembra o PIN sabe o que fazer e a quem pedir. -->
    <div v-if="forced" class="grid gap-2" data-pin-change-exits>
      <div class="flex flex-wrap justify-center gap-x-2">
        <NuxtButton
          color="neutral"
          variant="ghost"
          icon="i-lucide-user-round"
          :label="`Não é ${operatorName}? Trocar de usuário`"
          data-pin-change-switch-user
          @click="emit('switchUser')"
        />
        <NuxtButton
          color="neutral"
          variant="ghost"
          icon="i-lucide-circle-help"
          label="Esqueci meu PIN"
          :aria-expanded="forgot ? 'true' : 'false'"
          data-pin-change-forgot
          @click="forgot = !forgot"
        />
      </div>
      <NuxtAlert
        v-if="forgot"
        color="info"
        variant="subtle"
        icon="i-lucide-key-round"
        title="Peça a um gerente para redefinir o seu PIN"
        description="No Admin, em Credenciais PIN, a ação Resetar PIN gera um PIN temporário. Digite esse PIN aqui como PIN atual e escolha o novo."
        :actions="alertActions('info', [resetHref ? { label: 'Abrir no Admin', to: resetHref, target: '_blank', icon: 'i-lucide-external-link' } : null])"
        close
        data-pin-change-forgot-help
        @update:open="forgot = false"
      />
    </div>
  </div>
</template>
