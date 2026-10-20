<script setup lang="ts">
import type { ExecutionPatch, ExecutionSheetProjection } from "~/types/recipeBook";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import { useDirtyForm } from "../../../operator-kit/app/composables/useDirtyForm";
import { PRODUCTION_MODE_BATCH, PRODUCTION_MODE_HELP, PRODUCTION_MODE_OPTIONS } from "~/presentation/recipeBook";

const props = defineProps<{ open: boolean; execution: ExecutionSheetProjection | null; busy?: boolean }>();
const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: ExecutionPatch];
}>();

const form = reactive({
  maxStartedMinutes: "",
  capacityPerDay: "",
  requiresBatchTracking: false,
  shelfLifeDays: "",
  shelfLifeReviewed: false,
  productionLifecycle: "",
  productionMode: PRODUCTION_MODE_BATCH,
});
const initialShelfLife = ref("");
const { dirty, changedKeys, capture } = useDirtyForm(() => ({ ...form }));

watch(
  () => [props.open, props.execution?.revision],
  () => {
    if (!props.open || !props.execution) return;
    form.maxStartedMinutes = props.execution.max_started_minutes == null ? "" : String(props.execution.max_started_minutes);
    form.capacityPerDay = props.execution.capacity_per_day;
    form.requiresBatchTracking = props.execution.requires_batch_tracking;
    form.shelfLifeDays = props.execution.shelf_life_days == null ? "" : String(props.execution.shelf_life_days);
    initialShelfLife.value = form.shelfLifeDays;
    form.shelfLifeReviewed = props.execution.shelf_life_reviewed;
    form.productionLifecycle = props.execution.production_lifecycle;
    form.productionMode = props.execution.production_mode;
    nextTick(capture);
  },
  { immediate: true },
);

watch(
  () => form.shelfLifeDays,
  (value) => {
    if (value !== initialShelfLife.value && form.shelfLifeReviewed) form.shelfLifeReviewed = false;
  },
);

function integer(text: string, minimum: number, maximum: number): number | null | undefined {
  const clean = text.trim();
  if (!clean) return null;
  if (!/^\d+$/.test(clean)) return undefined;
  const value = Number(clean);
  return Number.isSafeInteger(value) && value >= minimum && value <= maximum ? value : undefined;
}

const maxStarted = computed(() => integer(form.maxStartedMinutes, 1, 10080));
const shelfLife = computed(() => integer(form.shelfLifeDays, 0, 3650));
const capacityValid = computed(() => {
  if (!form.capacityPerDay.trim()) return true;
  const value = Number(form.capacityPerDay.replace(",", "."));
  return Number.isFinite(value) && value > 0;
});
const valid = computed(() =>
  !!props.execution?.revision && maxStarted.value !== undefined && shelfLife.value !== undefined && capacityValid.value &&
  (!form.shelfLifeReviewed || shelfLife.value !== null),
);
const disabledReason = computed(() => {
  if (!props.execution?.revision) return "Publique uma versão antes de configurar a operação.";
  if (maxStarted.value === undefined) return "O tempo máximo precisa ser um número inteiro entre 1 e 10.080 minutos.";
  if (!capacityValid.value) return "A capacidade precisa ser maior que zero.";
  if (shelfLife.value === undefined) return "A validade precisa ser um número inteiro entre 0 e 3.650 dias.";
  if (form.shelfLifeReviewed && shelfLife.value === null) return "Informe a validade antes de confirmar a revisão.";
  return "";
});

function save() {
  if (!valid.value || !props.execution) return;
  emit("save", {
    expectedRevision: props.execution.revision,
    maxStartedMinutes: maxStarted.value,
    capacityPerDay: form.capacityPerDay.trim() || null,
    requiresBatchTracking: form.requiresBatchTracking,
    shelfLifeDays: shelfLife.value,
    shelfLifeReviewed: form.shelfLifeReviewed,
    productionLifecycle: form.productionLifecycle,
    productionMode: form.productionMode,
  });
}
const productionModeOptions = computed(() => props.execution?.production_mode_options ?? [...PRODUCTION_MODE_OPTIONS]);
</script>

<template>
  <OperatorFormShell
    :open="open"
    title="Operação da ficha"
    size="wide"
    description="Como a receita se comporta no planejamento e no chão de produção."
    :dirty="dirty"
    :dirty-count="changedKeys.length"
    :busy="busy"
    save-label="Salvar operação"
    save-icon="i-lucide-save"
    :save-disabled="!valid"
    :save-disabled-reason="disabledReason"
    @update:open="emit('update:open', $event)"
    @save="save"
  >
    <OperatorFormSection section-key="planning" title="Planejamento" description="Limites que alimentam atraso e ocupação.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Modo de produção" :description="PRODUCTION_MODE_HELP" class="sm:col-span-2">
          <NuxtRadioGroup
            v-model="form.productionMode"
            :items="productionModeOptions"
            value-key="value"
            label-key="label"
            orientation="horizontal"
            data-testid="execution-production-mode"
          />
        </NuxtFormField>
        <NuxtFormField label="Tempo máximo de lote aberto (min)" description="Vazio usa o padrão da loja.">
          <NuxtInput v-model="form.maxStartedMinutes" inputmode="numeric" class="w-full" />
        </NuxtFormField>
        <NuxtFormField label="Capacidade por dia" description="Vazio deixa a ocupação sem teto próprio.">
          <NuxtInput v-model="form.capacityPerDay" inputmode="decimal" class="w-full" />
        </NuxtFormField>
        <NuxtFormField v-if="execution?.lifecycle_options.length" label="Ciclo de produção" class="sm:col-span-2">
          <NuxtSelect
            v-model="form.productionLifecycle"
            :items="execution.lifecycle_options"
            value-key="value"
            label-key="label"
            class="w-full"
          />
        </NuxtFormField>
        <NuxtCheckbox
          v-model="form.requiresBatchTracking"
          class="sm:col-span-2"
          label="Rastrear lote ao concluir a produção"
        />
      </div>
    </OperatorFormSection>

    <OperatorFormSection section-key="validity" title="Validade do lote" description="Zero significa mesmo dia; vazio não presume prazo.">
      <div class="grid gap-3">
        <NuxtFormField label="Validade (dias)">
          <NuxtInput v-model="form.shelfLifeDays" inputmode="numeric" class="w-full" />
        </NuxtFormField>
        <NuxtCheckbox
          v-model="form.shelfLifeReviewed"
          label="Prazo revisado pelo responsável"
          description="Alterar os dias exige uma nova confirmação."
        />
        <p v-if="execution?.shelf_life_reviewed_by" class="text-xs text-muted-foreground">
          Última revisão registrada por {{ execution.shelf_life_reviewed_by }}.
        </p>
      </div>
    </OperatorFormSection>
  </OperatorFormShell>
</template>
