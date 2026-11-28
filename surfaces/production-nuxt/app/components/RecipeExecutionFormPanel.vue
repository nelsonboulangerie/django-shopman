<script setup lang="ts">
import type { ExecutionPatch, ExecutionSheetProjection } from "~/types/recipeBook";
import { PRODUCTION_MODE_BATCH, PRODUCTION_MODE_HELP, PRODUCTION_MODE_OPTIONS } from "~/presentation/recipeBook";

const props = defineProps<{ execution: ExecutionSheetProjection | null; busy?: boolean }>();
const emit = defineEmits<{
  save: [payload: ExecutionPatch];
  "update:dirty": [dirty: boolean];
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
const baseline = ref("");

function snapshot(): string {
  return JSON.stringify(form);
}

watch(
  () => props.execution?.revision,
  () => {
    if (!props.execution) return;
    form.maxStartedMinutes = props.execution.max_started_minutes == null ? "" : String(props.execution.max_started_minutes);
    form.capacityPerDay = props.execution.capacity_per_day;
    form.requiresBatchTracking = props.execution.requires_batch_tracking;
    form.shelfLifeDays = props.execution.shelf_life_days == null ? "" : String(props.execution.shelf_life_days);
    initialShelfLife.value = form.shelfLifeDays;
    form.shelfLifeReviewed = props.execution.shelf_life_reviewed;
    form.productionLifecycle = props.execution.production_lifecycle;
    form.productionMode = props.execution.production_mode;
    baseline.value = snapshot();
    emit("update:dirty", false);
  },
  { immediate: true },
);

watch(form, () => emit("update:dirty", !!baseline.value && snapshot() !== baseline.value), { deep: true });

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
  <form class="grid gap-3" @submit.prevent="save">
    <section class="grid gap-3 rounded-md border bg-card p-3">
      <div>
        <h2 class="text-sm font-semibold">Planejamento</h2>
        <p class="text-xs text-muted-foreground">Como a receita ocupa a produção e quando um lote exige atenção.</p>
      </div>
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
          <NuxtInput v-model="form.maxStartedMinutes" inputmode="numeric" class="w-full" :ui="{ base: 'bg-muted' }" />
        </NuxtFormField>
        <NuxtFormField label="Capacidade por dia" description="Vazio deixa a ocupação sem teto próprio.">
          <NuxtInput v-model="form.capacityPerDay" inputmode="decimal" class="w-full" :ui="{ base: 'bg-muted' }" />
        </NuxtFormField>
        <NuxtFormField v-if="execution?.lifecycle_options.length" label="Ciclo de produção" class="sm:col-span-2">
          <NuxtSelect
            v-model="form.productionLifecycle"
            :items="execution.lifecycle_options"
            value-key="value"
            label-key="label"
            class="w-full"
            :ui="{ base: 'bg-muted' }"
          />
        </NuxtFormField>
        <NuxtCheckbox
          v-model="form.requiresBatchTracking"
          class="sm:col-span-2"
          label="Rastrear lote ao concluir a produção"
        />
      </div>
    </section>

    <section class="grid gap-3 rounded-md border bg-card p-3">
      <div>
        <h2 class="text-sm font-semibold">Validade do lote</h2>
        <p class="text-xs text-muted-foreground">Zero significa mesmo dia; vazio não presume prazo.</p>
      </div>
      <div class="grid gap-3">
        <NuxtFormField label="Validade (dias)">
          <NuxtInput v-model="form.shelfLifeDays" inputmode="numeric" class="w-full" :ui="{ base: 'bg-muted' }" />
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
    </section>

    <div class="flex flex-wrap items-center justify-end gap-2">
      <p v-if="disabledReason" class="mr-auto text-xs text-destructive">{{ disabledReason }}</p>
      <NuxtButton
        type="submit"
        icon="i-lucide-save"
        label="Salvar configuração"
        :loading="busy"
        :disabled="!valid"
      />
    </div>
  </form>
</template>
