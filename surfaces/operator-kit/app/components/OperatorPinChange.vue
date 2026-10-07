<script setup lang="ts">
// Operator changes their own PIN on a stepped pad: current → new → confirm.
// Proving the current PIN is the authorization (enforced by the backend). Used
// voluntarily from the lock screen and forced after a manager reset (must-change).
// Pure UI — the parent owns the network call (changePin) and passes busy/error.
import { appendPinDigit } from "../presentation/operatorLock";

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

const canAdvance = computed(() => activeValue().trim().length >= 4);

function press(d: string) {
  localError.value = "";
  setActive(appendPinDigit(activeValue(), d));
}
function backspace() {
  setActive(activeValue().slice(0, -1));
}
function replaceActive(values: string[]) {
  setActive(
    values
      .filter((value) => /^[0-9]$/.test(value))
      .join("")
      .slice(0, 8),
  );
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
  <div>
    <NuxtAlert
      class="mb-3"
      color="neutral"
      variant="subtle"
      icon="i-lucide-key-round"
      :title="forced ? 'Defina um novo PIN' : 'Trocar meu PIN'"
      :description="
        forced
          ? 'O gerente resetou seu PIN. Digite o PIN temporário e escolha um novo antes de operar.'
          : `${operatorName}, informe o PIN atual e escolha um novo.`
      "
    />

    <div class="mb-2">
      <NuxtButton
        color="neutral"
        variant="link"
        icon="i-lucide-chevron-left"
        :label="step === 'current' ? 'Cancelar' : 'Voltar'"
        @click="back"
      />
    </div>

    <NuxtFormField :label="label">
      <NuxtPinInput
        :model-value="activeValue().split('')"
        :length="8"
        mask
        size="xl"
        @update:model-value="replaceActive"
      />
    </NuxtFormField>
    <NuxtAlert
      v-if="shownError"
      class="my-2"
      color="error"
      variant="subtle"
      :title="shownError"
    />

    <div class="grid grid-cols-3 gap-2">
      <NuxtButton
        v-for="d in ['1', '2', '3', '4', '5', '6', '7', '8', '9']"
        :key="d"
        color="neutral"
        variant="outline"
        size="xl"
        :label="d"
        @click="press(d)"
      />
      <NuxtButton
        color="neutral"
        variant="outline"
        size="xl"
        icon="i-lucide-delete"
        aria-label="Apagar o último dígito"
        @click="backspace"
      />
      <NuxtButton
        color="neutral"
        variant="outline"
        size="xl"
        label="0"
        @click="press('0')"
      />
      <NuxtButton
        size="xl"
        :icon="step === 'confirm' ? 'i-lucide-check' : 'i-lucide-arrow-right'"
        :disabled="!canAdvance || busy"
        :loading="busy"
        :aria-label="step === 'confirm' ? 'Confirmar o novo PIN' : 'Continuar'"
        @click="advance"
      />
    </div>
  </div>
</template>
