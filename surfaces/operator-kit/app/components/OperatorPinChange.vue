<script setup lang="ts">
// Operator changes their own PIN on a stepped pad: current → new → confirm.
// Proving the current PIN is the authorization (enforced by the backend). Used
// voluntarily from the lock screen and forced after a manager reset (must-change).
// Pure UI — the parent owns the network call (changePin) and passes busy/error.
import { PIN_MIN_DIGITS, appendPinDigit } from "../presentation/operatorLock";

const props = defineProps<{
  operatorName: string;
  forced?: boolean;
  busy?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  submit: [{ currentPin: string; newPin: string }];
  cancel: [];
}>();

type Step = "current" | "new" | "confirm";
const step = ref<Step>("current");
const currentPin = ref("");
const newPin = ref("");
const confirmPin = ref("");
const localError = ref("");

const label = computed(() => {
  if (step.value === "current")
    return props.forced ? "PIN temporário" : "PIN atual";
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

const canAdvance = computed(() => activeValue().trim().length >= PIN_MIN_DIGITS);

function press(d: string) {
  localError.value = "";
  setActive(appendPinDigit(activeValue(), d));
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
              ? "O gerente redefiniu seu PIN. Digite o PIN temporário e escolha um novo antes de operar."
              : `${operatorName}, informe o PIN atual e escolha um novo.`
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
  </div>
</template>
