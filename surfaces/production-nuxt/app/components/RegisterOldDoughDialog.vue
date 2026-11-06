<script setup lang="ts">
import type { RegisterOldDoughInput } from "~/composables/useProductionKds";
import { convertQuantity, normalizeQuantity, quantityRule } from "~/utils/quantity";

const props = withDefaults(
  defineProps<{
    open: boolean;
    workOrderLabel: string;
    positionRef?: string;
    busy?: boolean;
    /** Recusa do servidor por campo (error.issues), mostrada no próprio campo. */
    fieldErrors?: Partial<Record<"quantity" | "expiryDate" | "note" | "form", string>>;
  }>(),
  { positionRef: "", busy: false, fieldErrors: () => ({}) },
);

const emit = defineEmits<{
  "update:open": [open: boolean];
  submit: [input: RegisterOldDoughInput];
}>();

const quantity = ref<number | null>(null);
const unit = ref<"g" | "kg">("g");
const expiryDate = ref("");
const note = ref("");
const quantityInput = ref<{ inputRef?: { focus: () => void } } | null>(null);

const unitItems = [
  { label: "g", value: "g" },
  { label: "kg", value: "kg" },
];
// Teto de bancada: massa velha acima de 50 kg é dígito a mais (beta 05/11
// registrou 500999999999 g). O servidor tem a mesma régua.
const OLD_DOUGH_MAX_G = 50_000;
const maxQuantity = computed(() =>
  unit.value === "kg" ? OLD_DOUGH_MAX_G / 1000 : OLD_DOUGH_MAX_G,
);

function isoDay(offset: number): string {
  const date = new Date();
  date.setDate(date.getDate() + offset);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
function tomorrowIso(): string {
  return isoDay(1);
}
// A validade não pode estar no passado (hoje vale, como no servidor).
const minExpiry = computed(() => isoDay(0));

// A recusa do servidor vale para o número que ele recusou: mexeu no campo, a
// marca sai (senão o campo corrigido continua dizendo que está errado). A foto
// dos valores é tirada quando a recusa chega (watch abaixo do de abertura).
const rejected = ref<{ quantity: number | null; unit: string; expiryDate: string }>({
  quantity: null,
  unit: "g",
  expiryDate: "",
});
const quantityEdited = computed(
  () => quantity.value !== rejected.value.quantity || unit.value !== rejected.value.unit,
);
const expiryEdited = computed(() => expiryDate.value !== rejected.value.expiryDate);

const quantityError = computed(() => {
  if (quantity.value != null && quantity.value > maxQuantity.value) {
    return `Até ${unit.value === "kg" ? "50 kg" : "50.000 g"} por registro. Confira o número.`;
  }
  return quantityEdited.value ? "" : (props.fieldErrors.quantity ?? "");
});
const expiryError = computed(() => {
  if (expiryDate.value && expiryDate.value < minExpiry.value) {
    return "A validade não pode estar no passado.";
  }
  return expiryEdited.value ? "" : (props.fieldErrors.expiryDate ?? "");
});

const ready = computed(
  () =>
    quantity.value != null &&
    Number.isFinite(quantity.value) &&
    quantity.value > 0 &&
    quantity.value <= maxQuantity.value &&
    Boolean(expiryDate.value) &&
    expiryDate.value >= minExpiry.value,
);

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    quantity.value = null;
    unit.value = "g";
    expiryDate.value = tomorrowIso();
    note.value = "";
    void nextTick(() => quantityInput.value?.inputRef?.focus());
  },
  { immediate: true },
);
watch(
  () => props.fieldErrors,
  () => {
    rejected.value = {
      quantity: quantity.value,
      unit: unit.value,
      expiryDate: expiryDate.value,
    };
  },
  { immediate: true },
);

function onUnit(next: string) {
  const nextUnit = next === "kg" ? "kg" : "g";
  if (quantity.value != null) {
    quantity.value = convertQuantity(quantity.value, unit.value, nextUnit);
  }
  unit.value = nextUnit;
}

function submit() {
  if (!ready.value || props.busy) return;
  emit("submit", {
    quantity: String(normalizeQuantity(quantity.value ?? 0, unit.value)),
    unit: unit.value,
    expiryDate: expiryDate.value,
    positionRef: props.positionRef || undefined,
    note: note.value.trim() || undefined,
  });
}
</script>

<template>
  <NuxtModal
    :open="open"
    title="Registrar massa velha"
    :description="`${workOrderLabel}. A sobra pesada entra no estoque como um lote rastreável.`"
    :ui="{ content: 'sm:max-w-md' }"
    @update:open="emit('update:open', $event)"
  >
    <template #body>
      <div class="rounded-xl bg-white p-1">
        <div class="grid grid-cols-[minmax(0,1fr)_7rem] gap-3">
          <NuxtFormField label="Quantidade" required :error="quantityError || undefined">
            <NuxtInputNumber
              ref="quantityInput"
              v-model="quantity"
              :min="quantityRule(unit).min"
              :max="maxQuantity"
              :step="quantityRule(unit).step"
              :format-options="{
                maximumFractionDigits: quantityRule(unit).maximumFractionDigits,
              }"
              class="w-full"
              size="xl"
              :ui="{ base: 'bg-muted tabular-nums' }"
              aria-label="Quantidade de massa velha"
            />
          </NuxtFormField>
          <NuxtFormField label="Unidade" required>
            <NuxtSelect
              :model-value="unit"
              :items="unitItems"
              value-key="value"
              class="w-full"
              size="xl"
              :ui="{ base: 'bg-muted' }"
              aria-label="Unidade da massa velha"
              @update:model-value="onUnit"
            />
          </NuxtFormField>
        </div>

        <NuxtFormField
          label="Validade"
          required
          class="mt-4"
          :error="expiryError || undefined"
        >
          <UiDateField
            v-model="expiryDate"
            :min="minExpiry"
            class="w-full"
            label="Validade da massa velha"
          />
        </NuxtFormField>

        <NuxtFormField
          label="Nota (opcional)"
          class="mt-4"
          :error="fieldErrors.note || undefined"
        >
          <NuxtTextarea
            v-model="note"
            :rows="2"
            class="w-full"
            :ui="{ base: 'bg-muted' }"
            placeholder="Ex.: aparas do fim do turno"
          />
        </NuxtFormField>
        <!-- A recusa fica dentro do modal: o toast ficava atrás do overlay. -->
        <NuxtAlert
          v-if="fieldErrors.form"
          class="mt-4"
          color="error"
          variant="subtle"
          icon="i-lucide-circle-alert"
          :description="fieldErrors.form"
          data-old-dough-error
        />
      </div>
    </template>

    <template #footer>
      <div class="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        <NuxtButton
          color="neutral"
          variant="outline"
          size="xl"
          block
          label="Cancelar"
          @click="emit('update:open', false)"
        />
        <NuxtButton
          size="xl"
          block
          icon="i-lucide-package-plus"
          :disabled="!ready || busy"
          :loading="busy"
          label="Registrar"
          @click="submit"
        />
      </div>
    </template>
  </NuxtModal>
</template>
