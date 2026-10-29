<script setup lang="ts">
import type { RegisterOldDoughInput } from "~/composables/useProductionKds";
import { convertQuantity, normalizeQuantity, quantityRule } from "~/utils/quantity";

const props = withDefaults(
  defineProps<{
    open: boolean;
    workOrderLabel: string;
    positionRef?: string;
    busy?: boolean;
  }>(),
  { positionRef: "", busy: false },
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
const ready = computed(
  () =>
    quantity.value != null &&
    Number.isFinite(quantity.value) &&
    quantity.value > 0 &&
    Boolean(expiryDate.value),
);

function tomorrowIso(): string {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

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
          <NuxtFormField label="Quantidade" required>
            <NuxtInputNumber
              ref="quantityInput"
              v-model="quantity"
              :min="quantityRule(unit).min"
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

        <NuxtFormField label="Validade" required class="mt-4">
          <UiDateField
            v-model="expiryDate"
            class="w-full"
            label="Validade da massa velha"
          />
        </NuxtFormField>

        <NuxtFormField label="Nota (opcional)" class="mt-4">
          <NuxtTextarea
            v-model="note"
            :rows="2"
            class="w-full"
            :ui="{ base: 'bg-muted' }"
            placeholder="Ex.: aparas do fim do turno"
          />
        </NuxtFormField>
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
          label="Registrar massa velha"
          @click="submit"
        />
      </div>
    </template>
  </NuxtModal>
</template>
