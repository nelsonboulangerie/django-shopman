<script setup lang="ts">
import type {
  AuthorizeFormulaDeviationInput,
  AuthorizeFormulaDeviationResponse,
} from "~/composables/useProductionKds";
import type { ProductionFormulaLimitProjection } from "~/types/production";
import {
  normalizeQuantity,
  quantityRule,
  type QuantityUnit,
} from "~/utils/quantity";

const props = withDefaults(
  defineProps<{
    open: boolean;
    workOrderLabel: string;
    limits: ProductionFormulaLimitProjection[];
    result?: AuthorizeFormulaDeviationResponse | null;
    busy?: boolean;
  }>(),
  { result: null, busy: false },
);

const emit = defineEmits<{
  "update:open": [open: boolean];
  submit: [input: AuthorizeFormulaDeviationInput];
}>();

const ingredientRef = ref("");
const actualQuantity = ref<number | null>(null);
const batchRef = ref("");
const reason = ref("");
const actualInput = ref<{ inputRef?: { focus: () => void } } | null>(null);
const reasonInput = ref<{ textareaRef?: { focus: () => void } } | null>(null);

const ingredientItems = computed(() =>
  props.limits.map((limit) => ({
    label: `${limit.name} · ${limit.sku}`,
    value: limit.ingredient_ref,
  })),
);
const selectedLimit = computed(() =>
  props.limits.find((limit) => limit.ingredient_ref === ingredientRef.value),
);
const requiresBatch = computed(() =>
  selectedLimit.value?.sku.startsWith("MASSA-VELHA-"),
);
const batchItems = computed(() =>
  (selectedLimit.value?.available_batches ?? []).map((batch) => ({
    label: `${batch.ref} · ${batch.quantity} ${batch.unit} · vence ${batch.expiry_date}`,
    value: batch.ref,
  })),
);
const actualRule = computed(() => {
  const limit = selectedLimit.value;
  if (limit?.kind === "ratio")
    return { step: 0.1, min: 0, maximumFractionDigits: 1 };
  if (["g", "kg", "ml", "L", "un"].includes(limit?.unit ?? ""))
    return { ...quantityRule(limit!.unit as QuantityUnit), min: 0 };
  return { step: 0.001, min: 0, maximumFractionDigits: 3 };
});
const ready = computed(
  () =>
    Boolean(selectedLimit.value) &&
    actualQuantity.value != null &&
    Number.isFinite(actualQuantity.value) &&
    actualQuantity.value >= 0 &&
    Boolean(reason.value.trim()) &&
    (!requiresBatch.value || Boolean(batchRef.value.trim())),
);

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    ingredientRef.value = props.limits[0]?.ingredient_ref ?? "";
    batchRef.value = "";
    reason.value = "";
  },
  { immediate: true },
);
watch(
  selectedLimit,
  (limit) => {
    const value = Number(limit?.actual || limit?.target || "");
    actualQuantity.value = Number.isFinite(value) ? value : null;
    batchRef.value = "";
    void nextTick(() => actualInput.value?.inputRef?.focus());
  },
  { immediate: true },
);

function limitValue(value: string, empty: string): string {
  return value ? `${value} ${selectedLimit.value?.unit ?? ""}` : empty;
}

function onBatch(value: string) {
  batchRef.value = value;
  void nextTick(() => reasonInput.value?.textareaRef?.focus());
}

function submit() {
  if (!ready.value || props.busy || !selectedLimit.value) return;
  const actual =
    selectedLimit.value.kind === "fixed" &&
    ["g", "kg", "ml", "L", "un"].includes(selectedLimit.value.unit)
      ? normalizeQuantity(
          actualQuantity.value ?? 0,
          selectedLimit.value.unit as QuantityUnit,
        )
      : Math.round(((actualQuantity.value ?? 0) + Number.EPSILON) * 10) / 10;
  emit("submit", {
    ingredientRef: selectedLimit.value.ingredient_ref,
    actualQuantity: String(actual),
    batchRef: batchRef.value.trim() || undefined,
    reason: reason.value.trim(),
  });
}
</script>

<template>
  <NuxtModal
    :open="open"
    title="Autorizar desvio"
    :description="`${workOrderLabel}. A receita será recalculada com a quantidade realmente usada.`"
    :ui="{ content: 'sm:max-w-lg' }"
    @update:open="emit('update:open', $event)"
  >
    <template #body>
      <div v-if="result" class="flex flex-col gap-4">
        <NuxtAlert
          color="success"
          variant="subtle"
          icon="i-lucide-circle-check"
          title="Desvio autorizado"
          :description="`${result.ingredient_name}: ${result.actual}. A fórmula efetiva do lote foi recalculada.`"
        />
        <section class="rounded-xl border border-border bg-white p-4">
          <h3 class="font-medium">Impacto na composição</h3>
          <ul class="mt-3 divide-y divide-border text-sm">
            <li
              v-for="line in result.impact.bom"
              :key="line.sku"
              class="flex items-center justify-between gap-3 py-2"
            >
              <span>{{ line.sku }}</span>
              <span class="tabular-nums text-muted-foreground">
                {{ line.quantity }} {{ line.unit }}
              </span>
            </li>
          </ul>
          <p v-if="result.impact.batch_ref" class="mt-3 text-sm text-muted-foreground">
            Lote consumido: {{ result.impact.batch_ref }}
          </p>
        </section>
      </div>

      <div v-else class="flex flex-col gap-4 rounded-xl bg-white p-1">
        <NuxtFormField label="Ingrediente" required>
          <NuxtSelect
            v-model="ingredientRef"
            :items="ingredientItems"
            value-key="value"
            class="w-full"
            size="xl"
            :ui="{ base: 'bg-muted' }"
          />
        </NuxtFormField>

        <section v-if="selectedLimit" class="grid grid-cols-3 gap-2" aria-label="Limites da receita">
          <div class="rounded-lg bg-muted p-3">
            <p class="text-xs text-muted-foreground">Mínimo</p>
            <p class="mt-1 font-medium tabular-nums">{{ limitValue(selectedLimit.minimum, 'Sem piso') }}</p>
          </div>
          <div class="rounded-lg bg-muted p-3">
            <p class="text-xs text-muted-foreground">Alvo</p>
            <p class="mt-1 font-medium tabular-nums">{{ limitValue(selectedLimit.target, 'Não definido') }}</p>
          </div>
          <div class="rounded-lg bg-muted p-3">
            <p class="text-xs text-muted-foreground">Máximo</p>
            <p class="mt-1 font-medium tabular-nums">{{ limitValue(selectedLimit.maximum, 'Sem teto') }}</p>
          </div>
          <p v-if="selectedLimit.basis_label" class="col-span-3 text-xs text-muted-foreground">
            Base: {{ selectedLimit.basis_label }}
          </p>
        </section>

        <NuxtFormField label="Quantidade real" required>
          <div class="flex w-full items-stretch">
            <NuxtInputNumber
              ref="actualInput"
              v-model="actualQuantity"
              :min="actualRule.min"
              :step="actualRule.step"
              :format-options="{
                maximumFractionDigits: actualRule.maximumFractionDigits,
              }"
              class="min-w-0 flex-1"
              size="xl"
              :ui="{ base: 'rounded-r-none bg-muted tabular-nums' }"
              :aria-label="`Quantidade real em ${selectedLimit?.unit || 'unidade da receita'}`"
            />
            <span
              class="inline-flex items-center rounded-r-md border border-l-0 border-border bg-muted px-3 text-sm text-muted-foreground"
              aria-hidden="true"
            >{{ selectedLimit?.unit }}</span>
          </div>
        </NuxtFormField>

        <NuxtFormField
          v-if="requiresBatch"
          label="Lote de massa velha"
          description="Informe o lote disponível que será consumido."
          required
        >
          <NuxtSelect
            v-if="batchItems.length"
            :model-value="batchRef"
            :items="batchItems"
            value-key="value"
            class="w-full"
            size="xl"
            :ui="{ base: 'bg-muted' }"
            placeholder="Selecione o lote disponível"
            @update:model-value="onBatch"
          />
          <NuxtAlert
            v-else
            color="error"
            variant="subtle"
            icon="i-lucide-package-x"
            description="Nenhum lote válido de massa velha tem saldo disponível."
          />
        </NuxtFormField>

        <NuxtFormField label="Motivo da autorização" required>
          <NuxtTextarea
            ref="reasonInput"
            v-model="reason"
            :rows="3"
            class="w-full"
            :ui="{ base: 'bg-muted' }"
            placeholder="Explique por que este lote pode seguir com o desvio."
          />
        </NuxtFormField>
      </div>
    </template>

    <template #footer>
      <div v-if="result" class="w-full">
        <NuxtButton block size="xl" label="Fechar" @click="emit('update:open', false)" />
      </div>
      <div v-else class="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        <NuxtButton
          color="neutral"
          variant="outline"
          size="xl"
          block
          label="Cancelar"
          @click="emit('update:open', false)"
        />
        <NuxtButton
          color="warning"
          size="xl"
          block
          icon="i-lucide-shield-check"
          :disabled="!ready || busy"
          :loading="busy"
          label="Autorizar e recalcular"
          @click="submit"
        />
      </div>
    </template>
  </NuxtModal>
</template>
